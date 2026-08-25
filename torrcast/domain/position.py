"""Предметная единица Position приёмника."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False
    state: str = ""
    #: Показ убрал с экрана сам зритель. Такой конец не воскрешают: своя авария и воля
    #: человека снаружи похожи, а различает их приёмник тем, что переживает потерю
    #: сессии (:func:`torrcast.adapters.chromecast.cast.viewer_closed._viewer_closed`).
    closed: bool = False

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0
