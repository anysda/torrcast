"""Человеческий ввод Telegram для сценария выбора картины."""

from __future__ import annotations

import secrets
import threading
from contextlib import suppress

from tgbot.i18n import i18n
from tgbot.telegram_api import TelegramApi
from tgbot.telegram_menu import TelegramMenu
from torrcast.adapters.choice_environment import _SystemChoiceEnvironment
from torrcast.domain.cancelled_error import CancelledError

#: 🔴 TC-926. Подсказка про Enter
#: (:func:`~torrcast.usecases.choice.default_line.default_line`) - речь ТЕРМИНАЛА: там
#: ответ вводят с клавиатуры, и без этой строки не узнать, что даст пустой ввод. В чате
#: клавиатуры нет вовсе, нажимают кнопки, и «Enter - «Мумия (1932)», пункт 1 из 10» -
#: подсказка про то, чего в чате не существует. Гасится ЗДЕСЬ, в окружении Telegram, а не
#: в продукте: консоли строка нужна ровно такой, какая она есть.
_ENTER_HINT = "Enter "


class TelegramChoiceEnvironment(_SystemChoiceEnvironment):
    """Оставляет правила выбора прежними, заменяя лишь терминальный ввод-вывод."""

    def __init__(self, api: TelegramApi, chat_id: str) -> None:
        self._api = api
        self._chat_id = chat_id
        self._condition = threading.Condition()
        self._session = ""
        self._answer: int | None = None
        self._cancelled = False
        self._menu: TelegramMenu | None = None
        self._command_id = 0
        self._message_ids: list[int] = []

    def begin(self, command_id: int) -> None:
        """Открыть независимый вопрос для новой команды чата."""
        with self._condition:
            self._session = secrets.token_hex(4)
            self._answer = None
            self._cancelled = False
            self._menu = None
            self._command_id = command_id
            self._message_ids = []

    @staticmethod
    def stdin_is_tty() -> bool:
        """В чате есть человек, хотя терминального устройства нет."""
        return True

    def menu(self) -> TelegramMenu:
        """Создать inline-карточку на один вопрос, с кнопкой отмены под списком."""
        self._menu = TelegramMenu(
            self._api,
            self._chat_id,
            self._callback_data,
            cancel={
                "text": i18n("cancel"),
                "callback_data": f"drop:{self._session}",
            },
        )
        return self._menu

    def write(self, line: str) -> None:
        """Довезти строку стража; открытую карточку дополнить на месте."""
        if line.startswith(_ENTER_HINT):
            return  # подсказка про клавиатуру, которой в чате нет (:data:`_ENTER_HINT`)
        if self._menu is not None and self._menu.message_id:
            self._menu.note(line)
        else:
            message_id = self._api.send(self._chat_id, line, reply_to_message_id=self._command_id)
            if message_id:
                self._message_ids.append(message_id)

    def clean_search(self) -> None:
        """Убрать весь предпоказный диалог: строки поиска и карточку меню, если была."""
        ids = list(self._message_ids)
        if self._menu is not None and self._menu.message_id:
            ids.append(self._menu.message_id)
        for message_id in ids:
            with suppress(Exception):
                self._api.delete(self._chat_id, message_id)
        self._message_ids = []
        self._menu = None

    def clean(self) -> None:
        """Убрать весь диалог показа, включая исходную команду человека."""
        ids: list[int] = []
        if self._menu is not None and self._menu.message_id:
            ids.append(self._menu.message_id)
        if self._command_id:
            ids.append(self._command_id)
        ids.extend(self._message_ids)
        for message_id in dict.fromkeys(ids):
            with suppress(Exception):
                self._api.delete(self._chat_id, message_id)
        self._message_ids = []
        self._menu = None
        self._command_id = 0

    def command_id(self) -> int:
        """Номер сообщения нынешней команды: наблюдатель запоминает его на старте показа."""
        return self._command_id

    def clean_command(self, command_id: int) -> None:
        """Снять сообщение команды, чей показ кончился; нынешнюю чужую не трогать.

        Зовёт наблюдатель с номером, запомненным на СТАРТЕ кончившегося показа:
        если чат уже заняла следующая команда, её сообщение остаётся - её показ
        ещё не кончался и даже не начался.
        """
        if not command_id:
            return
        with suppress(Exception):
            self._api.delete(self._chat_id, command_id)
        if command_id == self._command_id:
            self._command_id = 0

    def ask(self, question: str, count: int, default: int | None = 1) -> int:
        """Ждать callback человека вместо чтения stdin; отмену поднять своим родом."""
        del question, default
        with self._condition:
            answered = self._condition.wait_for(
                lambda: self._answer is not None or self._cancelled, timeout=300
            )
            if self._cancelled:
                # 🔴 TC-926. Отмена возвращается из ожидания ОТДЕЛЬНЫМ родом, а не номером
                # и не отказом: номера у неё нет, а отказ уехал бы в чат строкой «Каст не
                # начался». Дальше её несёт код возврата (:data:`EXIT_CANCELLED`).
                raise CancelledError(i18n("cancelled"))
            if not answered or self._answer is None:
                raise self.not_found_error(i18n("choice_timeout"))
            if not 1 <= self._answer <= count:
                raise self.not_found_error(i18n("choice_expired"))
            return self._answer

    def cancel(self, data: str, message_id: int) -> bool:
        """Принять отмену лишь от нынешней карточки и вывести выбор из ожидания."""
        if (
            data != f"drop:{self._session}"
            or self._menu is None
            or message_id != self._menu.message_id
        ):
            return False
        with self._condition:
            self._cancelled = True
            self._condition.notify_all()
        return True

    def accept(self, data: str, message_id: int) -> bool:
        """Принять ответ лишь от нынешней карточки и разбудить выбор."""
        prefix = f"pick:{self._session}:"
        if (
            not data.startswith(prefix)
            or self._menu is None
            or message_id != self._menu.message_id
            or self._cancelled  # вопрос уже снят: отвечать нечему, карточка уходит
        ):
            return False
        try:
            number = int(data.removeprefix(prefix))
        except ValueError:
            return False
        self._menu.chosen(number)
        with self._condition:
            self._answer = number
            self._condition.notify_all()
        return True

    def _callback_data(self, number: int, _message_id: int) -> str:
        """Уложить адрес ответа в короткий callback Telegram."""
        return f"pick:{self._session}:{number}"
