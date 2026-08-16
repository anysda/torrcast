"""Даёт тестам управляемые монотонное время, стенные часы и ожидание."""

from dataclasses import dataclass, field


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)
    wall_now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def wall(self) -> float:
        return self.wall_now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
