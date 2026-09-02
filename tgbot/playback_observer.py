"""Сводит Telegram-пульт с межпроцессным снимком настоящего показа."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Final

from tgbot.telegram_control import TelegramControl, _TelegramError

if TYPE_CHECKING:
    from tgbot.telegram_choice_environment import TelegramChoiceEnvironment

_INTERVAL: Final = 2.0
#: Смена РОДА отказа называется, лишь устоявшись: одиночный тик чужого рода
#: (скажем, один ReadTimeout среди сплошных 401) - сетевой шум, а не новая беда.
_STEADY_TICKS: Final = 3


class PlaybackObserver:
    """Следит за показом независимо от занятого запуском главного потока бота."""

    def __init__(
        self,
        control: TelegramControl,
        title: Callable[[], str],
        choice: TelegramChoiceEnvironment | None = None,
        interval: float = _INTERVAL,
    ) -> None:
        self._control = control
        self._title = title
        self._choice = choice
        self._interval = interval
        self._shown = ""
        self._refused = ""
        self._pending = ("", 0)
        #: Команда, начавшая нынешний показ: её сообщение убирается с концом показа.
        self._command = 0

    def sync(self, title: str | None = None) -> None:
        """Одним шагом привести сообщение к текущему снимку продукта.

        Отказ Telegram глушится (следующий тик повторит попытку), но не бесследно:
        он называется в журнале один раз на смену состояния (:meth:`_note`).
        Кончившийся показ забирает и сообщение своей команды: конец показа обязан
        выглядеть в чате так же, как остановка руками. Номер запоминается на СТАРТЕ
        показа: команде, занявшей чат после, сноситься рано - её показ ещё не шёл.
        """
        title = self._title() if title is None else title
        try:
            if title:
                if not self._shown and self._choice is not None:
                    self._command = self._choice.command_id()
                self._control.show(title)
            else:
                self._control.clean()
                if self._shown and self._choice is not None:
                    self._choice.clean_command(self._command)
        except _TelegramError as refusal:
            self._note(str(refusal))
        else:
            self._note("")
        self._shown = title

    def run(self) -> None:
        """Бесконечно сверять снимок; временный отказ чтения не убивает наблюдателя."""
        while True:
            with suppress(Exception):
                self.sync()
            threading.Event().wait(self._interval)

    def _note(self, refusal: str) -> None:
        """Назвать беду один раз при смене состояния, а не на каждом тике цикла.

        Повторяющийся каждые две секунды отказ - одна строка; вернувшаяся работа -
        тоже одна. Смена РОДА отказа (сеть ожила, а токен всё ещё мёртв) называется,
        лишь устоявшись на нескольких тиках подряд: одиночный чужой тик - шум
        сети, а не новая беда, иначе журнал снова превращается в спам. Без этого
        отказ Telegram читался бы как «просто нет показа».
        """
        if not refusal:
            if self._refused:
                self._say("")
                self._refused = ""
            self._pending = ("", 0)
            return
        if refusal == self._refused:
            self._pending = ("", 0)
            return
        if not self._refused:
            self._say(refusal)
            self._refused = refusal
            return
        pending, count = self._pending
        if refusal != pending:
            self._pending = (refusal, 1)
            return
        count += 1
        self._pending = (refusal, count)
        if count >= _STEADY_TICKS:
            self._say(refusal)
            self._refused = refusal
            self._pending = ("", 0)

    @staticmethod
    def _say(refusal: str) -> None:
        """Оставить строку в журнале; токен в текст отказа не попадает."""
        # Локальный импорт - без цикла: каталоги фраз тянут за собой полпродукта.
        from torrcast.domain.catalogs.phrase import phrase

        if refusal:
            line = phrase("telegram.observer_refused", detail=refusal)
        else:
            line = phrase("telegram.observer_recovered")
        print(line, file=sys.stderr, flush=True)
