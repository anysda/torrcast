"""Ввод и вывод, нужные сценарию ранжирования."""

from typing import Protocol


class RankEnvironment(Protocol):
    """Показывает текст и выбирает звуковую дорожку."""

    def write(self, message: str) -> None: ...

    def choose(self, question: str, count: int, default: int) -> int: ...
