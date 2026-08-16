"""Предметная единица Position приёмника."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False
    state: str = ""

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0
