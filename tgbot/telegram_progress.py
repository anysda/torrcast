"""Редкий Telegram-индикатор всех фаз одного запуска в одном сообщении."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import suppress
from types import TracebackType
from typing import Final

from tgbot.telegram_api import TelegramApi
from torrcast.domain.catalogs.phrase import phrase

_TICK: Final = 5.0


class TelegramProgress:
    """Общая доска фаз: завод порта выдаёт ей лёгкие отдельные ручки."""

    def __init__(
        self,
        api: TelegramApi,
        chat_id: str,
        tick: float = _TICK,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api = api
        self._chat_id = chat_id
        self._tick = tick
        self._clock = clock
        self._message_id = 0
        self._notes: list[str] = []
        self._phase = ""
        self._since = 0.0
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()

    def begin(self) -> None:
        """Очистить доску перед новым запросом, не создавая сообщения заранее."""
        self.finish()
        with self._lock:
            self._notes = []

    def new(self) -> _TelegramProgress:
        """Дать очередной фазе отдельную ручку общего сообщения."""
        return _TelegramProgress(self)

    def phase(self, text: str) -> None:
        """Сменить текущую ступень и запустить редкий тик при необходимости."""
        with self._lock:
            if text == self._phase:
                return
            self._phase, self._since = text, self._clock()
            if text:
                self._draw()
                if self._thread is None:
                    self._thread = threading.Thread(
                        target=self._run, daemon=True, name="telegram-progress"
                    )
                    self._thread.start()

    def note(self, text: str) -> None:
        """Оставить решение над бегущей фазой и поправить прежнее сообщение."""
        with self._lock:
            self._notes.append(text)
            self._draw()

    def finish(self, text: str = "") -> None:
        """Убрать успешный прогресс либо заменить его сообщением об отказе."""
        with self._lock:
            self._phase = ""
            if text:
                if self._message_id:
                    self._api.edit(self._chat_id, self._message_id, text)
                else:
                    self._message_id = self._api.send(self._chat_id, text)
            elif self._message_id:
                with suppress(Exception):
                    self._api.delete(self._chat_id, self._message_id)
                self._message_id = 0
        self._wake.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._wake.clear()

    def _run(self) -> None:
        while not self._wake.wait(self._tick):
            with self._lock:
                if self._phase:
                    self._draw()

    def _draw(self) -> None:
        if not self._phase and not self._notes:
            return
        lines = self._notes[-12:]
        if self._phase:
            spent = self._clock() - self._since
            lines.append(f"{self._phase}... {spent:.0f} {phrase('console.seconds')}")
        text = "\n".join(lines)
        if self._message_id:
            self._api.edit(self._chat_id, self._message_id, text)
        else:
            self._message_id = self._api.send(self._chat_id, text)


class _TelegramProgress:
    """Одна фазовая ручка, соответствующая договору порта Progress."""

    def __init__(self, board: TelegramProgress) -> None:
        self._board = board

    def phase(self, text: str) -> None:
        self._board.phase(text)

    def note(self, text: str) -> None:
        self._board.note(text)

    def stop(self) -> None:
        self._board.phase("")

    def __enter__(self) -> _TelegramProgress:
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _error: BaseException | None,
        _trace: TracebackType | None,
    ) -> None:
        self.stop()
