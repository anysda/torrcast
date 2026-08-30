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
    #: Свежего слова приёмник не дал: сокет лёг, и поля выше - эхо прошлого опроса, а не
    #: ответ про сейчас (:meth:`torrcast.adapters.chromecast.cast.receiver_link._Link._status`).
    #: 🔴 Молчит такой ответ ровно об одном - о воле зрителя: :attr:`closed` в нём всегда
    #: ``False``, потому что на экране числится ещё НАШЕ приложение из прошлого статуса, а
    #: вовсе не потому, что показ не закрывали. Замер на приставке 30-08-2026: жест пультом,
    #: первый же тёмный опрос отвечает ``closed=False`` при мёртвом сокете, и лишь
    #: следующий, переподключившийся, называет волю человека (TC-880).
    stale: bool = False

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0
