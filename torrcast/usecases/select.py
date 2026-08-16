"""Запускает отбор пригодного релиза через переданную зависимость."""

from collections.abc import Callable
from typing import Generic, TypeVar

Request = TypeVar("Request")
Result = TypeVar("Result")


class Select(Generic[Request, Result]):
    """Сценарий выбора первого пригодного релиза из подготовленного плана."""

    def __init__(self, select: Callable[[Request], Result]) -> None:
        self._select = select

    def run(self, request: Request) -> Result:
        """Возвращает результат отбора для одного плана."""
        return self._select(request)


__all__ = ["Select"]
