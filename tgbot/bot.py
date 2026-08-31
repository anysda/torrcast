"""Polling-бот: команда чата, inline-выбор и запуск torrcast."""

from __future__ import annotations

import shlex
import threading
from collections.abc import Callable, Sequence
from queue import Queue
from typing import Any

from tgbot.config import Config
from tgbot.i18n import _failure_detail, i18n
from tgbot.restore_flag_dashes import restore_flag_dashes
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_choice_environment import TelegramChoiceEnvironment
from tgbot.telegram_control import TelegramControl
from torrcast.cli.main import main as run_cast
from torrcast.domain.exit_codes import EXIT_CANCELLED
from torrcast.runtime.playback_session import playback_session
from torrcast.runtime.wire import wire
from torrcast.usecases.choice.configure import configure as configure_choice

_Command = Callable[[Sequence[str] | None], int]


def _playing_title() -> str:
    """Взять название и год из структурированного состояния продукта."""
    session = playback_session()
    shown = session.snapshot(session.key() if session.active() else "")
    if shown is None:
        return ""
    year = f" ({shown.year})" if shown.year else ""
    return shown.title + year + (f" {shown.label}" if shown.label else "")


class Bot:
    """Один обработчик группы; polling передаёт команды главному потоку очередью."""

    def __init__(
        self,
        config: Config,
        *,
        api: TelegramApi | None = None,
        command: _Command = run_cast,
        assemble: Callable[[], None] = wire,
        title: Callable[[], str] = _playing_title,
    ) -> None:
        self._config = config
        self._api = api or TelegramApi(config.token, config.proxy, timeout=25.0)
        self._command = command
        self._title = title
        assemble()
        self._choice = TelegramChoiceEnvironment(self._api, config.chat_id)
        self._control = TelegramControl(self._api, config.chat_id)
        configure_choice(self._choice)
        self._offset = 0
        self._commands: Queue[list[str]] = Queue()
        self._busy = False
        self._busy_lock = threading.Lock()

    def run(self) -> None:
        """Оставить CLI главный поток, а получение callback вынести в рабочий."""
        threading.Thread(target=self.poll, daemon=True, name="telegram-polling").start()
        while True:
            self.run_one()

    def run_one(self) -> None:
        """Исполнить следующую команду там, откуда вызван цикл команд."""
        args = self._commands.get()
        try:
            self._run(args)
        finally:
            with self._busy_lock:
                self._busy = False
            self._commands.task_done()

    def poll(self) -> None:
        """Получать обновления бесконечно; каждый offset подтверждать один раз."""
        while True:
            for update in self._api.updates(self._offset):
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                self.dispatch(update)

    def dispatch(self, update: dict[str, Any]) -> None:
        """Отсечь чужой чат и развести сообщение с callback."""
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            self._callback(callback)
            return
        message = update.get("message")
        if isinstance(message, dict):
            self._message(message)

    def _message(self, message: dict[str, Any]) -> None:
        chat = message.get("chat")
        text = message.get("text")
        if not isinstance(chat, dict) or str(chat.get("id")) != self._config.chat_id:
            return
        if not isinstance(text, str) or (
            text.casefold() != "cast" and not text.casefold().startswith("cast ")
        ):
            return
        # Язык - настройка продукта, а не свойство клиента чата: по `language_code`
        # у владельца один ответ выходил двумя языками разом. Спрашивает его сама
        # надпись у единого держателя, при каждом ответе заново: бот живёт долго, и
        # `cast --ru`, посланный из этого же чата или с консоли, обязан подействовать
        # со следующей же команды, а не после рестарта юнита (:mod:`tgbot.i18n`).
        try:
            args = shlex.split(restore_flag_dashes(text))[1:]
        except ValueError as error:
            self._api.send(self._config.chat_id, i18n("failed", detail=str(error)))
            return
        if not args:
            self._api.send(self._config.chat_id, i18n("help"))
            return
        message_id = message.get("message_id")
        command_id = int(message_id) if isinstance(message_id, int) else 0
        begin_choice = args != ["stop"]
        if not self._enqueue(args, begin_choice=begin_choice, command_id=command_id):
            self._api.send(self._config.chat_id, i18n("busy"))
            return

    def _callback(self, callback: dict[str, Any]) -> None:
        message = callback.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat")
        if not isinstance(chat, dict) or str(chat.get("id")) != self._config.chat_id:
            return
        callback_id, data = callback.get("id"), callback.get("data")
        if not isinstance(callback_id, str) or not isinstance(data, str):
            return
        controlled = self._control.command(data)
        if controlled is not None:
            if controlled == "stop":
                self._enqueue(["stop"])
            self._api.answer(callback_id, i18n("control_done"))
            return
        message_id = int(message.get("message_id", 0))
        if self._choice.cancel(data, message_id):
            # 🔴 TC-926. Отмена отвечается ВСПЛЫВАЮЩЕЙ подсказкой, а не сообщением: сам
            # диалог сейчас будет убран целиком (:meth:`_run`), и новое сообщение в чате
            # пережило бы уборку мусором. Подсказка следа за собой не оставляет.
            self._api.answer(callback_id, i18n("cancelled"))
            return
        accepted = self._choice.accept(data, message_id)
        self._api.answer(callback_id, i18n("chosen" if accepted else "choice_expired"))

    def _run(self, args: list[str]) -> None:
        """Исполнить настоящую команду torrcast и назвать отказ в чате."""
        try:
            code = self._command(args)
        except Exception as error:
            self._api.send(
                self._config.chat_id,
                i18n("failed", detail=_failure_detail(error)),
            )
            return
        if code == EXIT_CANCELLED:
            # 🔴 TC-926. Человек передумал - в чат не летит ничего, а весь предпоказный
            # диалог убирается целиком, тем же порядком, что и по ⏹. Код назван ПОИМЁННО:
            # промолчи бот на любой ненулевой - и настоящий отказ ушёл бы в ту же тишину.
            self._choice.clean()
        elif code:
            self._api.send(self._config.chat_id, i18n("failed", detail=str(code)))
        elif args == ["stop"]:
            self._control.clean()
            self._choice.clean()
        else:
            title = self._title()
            if title:
                self._choice.clean_search()
                self._control.show(title)

    def _enqueue(
        self,
        args: list[str],
        *,
        begin_choice: bool = False,
        command_id: int = 0,
    ) -> bool:
        """Занять единственный исполнитель и передать ему команду без гонки."""
        with self._busy_lock:
            if self._busy:
                return False
            self._busy = True
            if begin_choice:
                self._choice.begin(command_id)
        self._commands.put(args)
        return True


def _bot() -> None:
    """Прочитать проверенную настройку и запустить polling."""
    Bot(Config.load()).run()
