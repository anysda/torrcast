"""Управляет выбранным сценариями приёмником воспроизведения."""

from typing import Protocol

from torrcast.domain.position import Position


class Receiver(Protocol):
    def play(self, url: str, title: str = "", at: float = 0.0) -> None: ...
    def stop(self, quit_app: bool = False) -> None: ...
    def position(self, front: float = 0.0) -> Position: ...
