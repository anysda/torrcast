"""Изображает для тестов приёмник и записывает команды управления."""

from dataclasses import dataclass, field

from torrcast.domain.position import Position


@dataclass
class FakeReceiver:
    current: Position
    plays: list[tuple[str, str, float]] = field(default_factory=list)
    stops: list[bool] = field(default_factory=list)
    fronts: list[float] = field(default_factory=list)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        self.plays.append((url, title, at))

    def stop(self, quit_app: bool = False) -> None:
        self.stops.append(quit_app)

    def position(self, front: float = 0.0) -> Position:
        self.fronts.append(front)
        return self.current
