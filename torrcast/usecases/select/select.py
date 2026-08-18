"""Сценарий отбора: вызывает переданную реализацию."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

Request = TypeVar("Request")


Result = TypeVar("Result")


class Select(Generic[Request, Result]):
    """Вызывает переданную реализацию сценария отбора."""

    def __init__(self, select: Callable[[Request], Result]) -> None:
        self._select = select

    def run(self, request: Request) -> Result:
        """Отбирает результат для запроса."""
        return self._select(request)
