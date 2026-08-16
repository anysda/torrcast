"""Даёт сценариям ввод и вывод через консоль."""

from typing import Protocol


class Console(Protocol):
    def ask(self, question: str, default: str = "") -> str: ...
    def write(self, message: str) -> None: ...
