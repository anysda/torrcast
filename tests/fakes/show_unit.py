"""Изображает юнит показа для ожидания картинки: живость, причина и остановка."""

from dataclasses import dataclass, field


@dataclass
class FakeShowUnit:
    alive: bool = True
    reason: str = "юнит ещё идёт к картинке"
    stops: list[int] = field(default_factory=list)

    def active(self) -> bool:
        return self.alive

    def why(self) -> str:
        return self.reason

    def stop(self) -> None:
        self.stops.append(1)
        self.alive = False
