"""Повторяет запуск погасшего показа через часы и приёмник."""

from dataclasses import dataclass

from torrcast.ports.clock import Clock
from torrcast.ports.receiver import Receiver


@dataclass(slots=True)
class Revive:
    """Выдерживает заданную паузу и повторяет LOAD с сохранённого места."""

    receiver: Receiver
    clock: Clock

    def run(self, url: str, title: str, position: float, pause: float) -> None:
        self.clock.sleep(pause)
        self.receiver.play(url, title, position)
