"""Единственная полоса команд Telegram: идущая работа и один последний заказ."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class _QueuedCommand:
    """Команда чата и условие, после которого ей безопасно начинаться."""

    args: list[str]
    text: str
    command_id: int = 0
    begin_choice: bool = False
    barrier: threading.Event | None = None


class CommandLane:
    """Держать исполняемую команду и заменяемый последний запрос без гонки."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._active: _QueuedCommand | None = None
        self._pending: _QueuedCommand | None = None
        self._barrier: threading.Event | None = None

    def offer(self, command: _QueuedCommand) -> bool:
        """Взять команду только на свободную полосу."""
        with self._condition:
            if self._active is not None or self._pending is not None:
                return False
            self._pending = command
            self._condition.notify()
            return True

    def replace(self, command: _QueuedCommand, call_off: Callable[[], threading.Event]) -> str:
        """Оставить последнюю команду, сняв идущую и прежнюю ожидающую."""
        with self._condition:
            occupied = self._pending or self._active
            if occupied is None:
                self._pending = command
                self._condition.notify()
                return ""
            if self._active is not None and self._barrier is None:
                self._barrier = call_off()
            command = replace(command, barrier=self._barrier)
            previous = occupied.text
            self._pending = command
            self._condition.notify()
            return previous

    def take(self) -> _QueuedCommand:
        """Взять следующий заказ для единственного исполнителя."""
        with self._condition:
            self._condition.wait_for(lambda: self._pending is not None)
            command = self._pending
            assert command is not None
            self._active = command
            self._pending = None
        return command

    def finish(self, command: _QueuedCommand) -> None:
        """Освободить исполнителя, сохранив уже ожидающую замену."""
        with self._condition:
            if self._active is command:
                self._active = None
            if self._pending is None:
                self._barrier = None

    def occupied(self) -> str:
        """Чем полоса занята с точки зрения последнего принятого заказа."""
        with self._condition:
            command = self._pending or self._active
            return command.text if command is not None else ""


QueuedCommand = _QueuedCommand
