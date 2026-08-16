"""Даёт сценариям монотонное время и ожидание."""

from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...
