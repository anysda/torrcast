"""Предметная единица Receiver приёмника."""

from typing import Protocol, runtime_checkable

from torrcast.domain.position import Position


@runtime_checkable
class Receiver(Protocol):
    """Что нам нужно от приёмника — и ничего сверх того."""

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        """Начать воспроизведение HLS-манифеста с секунды ``at``."""

    def stop(self, quit_app: bool = False) -> None:
        """Снять каст; ``quit_app`` — ещё и закрыть приложение приёмника.

        ``quit_app=False`` — показ передают дальше (стык серий): приложение остаётся
        открытым, следующая серия грузится в него же.
        """

    def position(self, front: float = 0.0) -> Position:
        """Текущая позиция и длительность; ``front`` — докуда упаковано."""
