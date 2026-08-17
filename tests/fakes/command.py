"""Команда CLI без аргументов: считает вызовы и отдаёт заранее заданный код возврата."""

from dataclasses import dataclass


@dataclass
class FakeCommand:
    result: int = 0
    calls: int = 0

    def __call__(self) -> int:
        self.calls += 1
        return self.result
