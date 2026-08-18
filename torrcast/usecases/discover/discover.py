"""Сценарий поиска: вызывает переданную реализацию."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

Request = TypeVar("Request")


Result = TypeVar("Result")


class Discover(Generic[Request, Result]):
    """Вызывает переданную реализацию сценария поиска."""

    def __init__(self, discover: Callable[[Request], Result]) -> None:
        self._discover = discover

    def run(self, request: Request) -> Result:
        """Находит варианты для запроса."""
        return self._discover(request)
