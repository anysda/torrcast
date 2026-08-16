"""Запускает поиск и построение планов через переданную зависимость."""

from collections.abc import Callable
from typing import Generic, TypeVar

Request = TypeVar("Request")
Result = TypeVar("Result")


class Discover(Generic[Request, Result]):
    """Сценарий поиска фильма и подготовки вариантов выбора."""

    def __init__(self, discover: Callable[[Request], Result]) -> None:
        self._discover = discover

    def run(self, request: Request) -> Result:
        """Находит варианты для одного пользовательского запроса."""
        return self._discover(request)


__all__ = ["Discover"]
