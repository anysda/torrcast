"""Сводит Telegram-пульт с межпроцессным снимком настоящего показа."""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import suppress
from typing import Final

from tgbot.telegram_control import TelegramControl

_INTERVAL: Final = 2.0


class PlaybackObserver:
    """Следит за показом независимо от занятого запуском главного потока бота."""

    def __init__(
        self,
        control: TelegramControl,
        title: Callable[[], str],
        interval: float = _INTERVAL,
    ) -> None:
        self._control = control
        self._title = title
        self._interval = interval
        self._shown = ""

    def sync(self) -> None:
        """Одним шагом привести сообщение к текущему снимку продукта."""
        title = self._title()
        if title:
            self._control.show(title)
        else:
            self._control.clean()
        self._shown = title

    def run(self) -> None:
        """Бесконечно сверять снимок; временный отказ чтения не убивает наблюдателя."""
        while True:
            with suppress(Exception):
                self.sync()
            threading.Event().wait(self._interval)
