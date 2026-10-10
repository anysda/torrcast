"""Конец картинки, дочитанный после первого кадра: ни список кусков, ни старт его не ждут.

Ставит его медиатракт (:func:`torrcast.usecases.playback._tract._tract`) в ленту показа
(:attr:`torrcast.usecases.playback.ended_feed.EndedFeed.settle`); зовут его раздача перед
первым списком кусков и показ после LOAD (:meth:`_Ending.after_load`), а поздний паспорт
приходит сам, по готовности (:meth:`_Ending._late`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Final

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.playback._end_swap import SAME_EDGE, _layout, _swap
from torrcast.usecases.playback.ended_feed import EndedFeed
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.warm.warmer import Warmer
from torrcast.usecases.watch import Watch

#: Сколько паспорт ждёт первый кадр, если его не заметили: показ идёт, а конец нужен.
PICTURE_CAP: Final = 180.0


def _never() -> bool:
    return False


def _idle() -> None:
    return None


@dataclass(slots=True)
class _Ending:
    """Ставит конец картинки, как только паспорт готов, и пересобирает сетку впереди упаковки.

    🔴 Ни список кусков, ни LOAD паспорт не ждут: стенд 10-10, «Секс в большом городе» s2e5,
    холодный рой - приёмник попросил список через 3.7 с после упаковки, хвост файла читался
    ещё 8 с, и ровно на эти 8 с позже приёмник попросил первый кусок. Поздний паспорт
    пересобирает сетку сам, когда придёт, и только там, куда упаковка ещё не дошла: куски,
    которые уже лежат или пакуются, обязаны остаться теми же местами фильма. Список у
    приёмника тогда старый, но разойтись он может только хвостом, за последним кадром:
    последний кусок отдаётся по картинке, а номеров за ним в новой сетке нет, и раздача
    отвечает на них сразу (:func:`torrcast.usecases.feed_pack.feed_segment._segment`).
    Прогрев, уже отданный показу, остаётся своим: его куски сверяются с сеткой при выдаче.
    Сетка, разошедшаяся с прежней уже в голове (ровная против покадровой), не ставится
    вовсе - показ идёт по длительности контейнера, а паспорт ложится на полку для
    следующего показа того же файла.
    """

    ahead: Future[Media]
    watch: Watch
    supply: StreamSource | None
    relayout: Callable[[], tuple[MediaGrid, Encoding | None]]
    rebuild: Callable[..., tuple[SpotRecoder | None, Warmer | None]]
    feed: EndedFeed
    server: StreamServer
    receiver: Receiver
    recoder: SpotRecoder | None
    warmer: Warmer | None
    start: float
    picture: Callable[[], bool] = _never
    go: Callable[[], None] = _idle
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _began: float = field(default_factory=lambda: _state.CLOCK.monotonic())
    _asked: bool = False
    _settled: bool = False
    _warming: bool = False
    _pending: tuple[float, MediaGrid, int] | None = None
    _was: int = 0
    _went: bool = False

    def __call__(self) -> None:
        """Перед списком кусков: готовый паспорт ставится сразу, неготовый догонит сам."""
        with self._lock:
            if self._asked:
                return
            self._asked = True
            if self._settled:
                return
            if self.ahead.done():
                self._settle()
                return
            journal().mark("конец картинки опоздал", ждали=0.0)
        self.ahead.add_done_callback(self._late)

    @staticmethod
    def after_load(feed: EndedFeed, warmer: Warmer | None) -> Warmer | None:
        """Прогрев показа после LOAD - на той сетке, что есть сейчас, без ожидания паспорта."""
        if not isinstance(feed.settle, _Ending):
            return warmer
        return feed.settle.hand()

    def hand(self) -> Warmer | None:
        """Отдать прогрев показу: готовый паспорт ставится до этого, после - прогрев свой."""
        with self._lock:
            if not self._settled and self.ahead.done():
                self._settle()
            elif not self._settled and not self._asked:
                self._asked = True
                journal().mark("конец картинки опоздал", ждали=0.0)
                self.ahead.add_done_callback(self._late)
            self._warming = True
            return self.warmer

    def _late(self, _ahead: Future[Media]) -> None:
        """Паспорт пришёл после списка: новая сетка ждёт, пока упаковка дойдёт до расхождения."""
        with self._lock:
            if self._settled:
                return
            self._settled = True
            end = self._end()
            if end is None or abs(end - self.watch.entry.dur) <= SAME_EDGE:
                return
            grid, cut = _layout(self, end)
            if cut <= self.feed.door:
                journal().mark("сетка по картинке не встала", дверь=self.feed.door, расхождение=cut)
                return
            self._pending = (end, grid, cut)
            journal().mark("сетка по картинке ждёт упаковку", расхождение=cut)

    def tick(self) -> None:
        """По часам показа: картинка на экране - пустить паспорт; упаковка дошла до куска
        перед расхождением - встать на новую сетку."""
        with self._lock:
            if not self._went:
                waited = round(_state.CLOCK.monotonic() - self._began, 2)
                if self.picture() or waited >= PICTURE_CAP:
                    self._went = True
                    journal().mark("паспорт пошёл", через=waited)
                    self.go()
            if self._pending is None:
                return
            end, grid, cut = self._pending
            feed, packer = self.feed, self.feed.packer
            live = packer is not None and not packer.halted and packer.poll() is None
            first, edge = (packer.first, packer.edge) if live and packer is not None else (0, cut)
            if first <= cut and edge < cut - 1:
                return  # упаковка ещё не дошла до куска перед расхождением
            self._pending = None
            if cut <= feed.door or feed.have(cut) or first > cut:
                journal().mark("сетка по картинке не встала", дверь=feed.door, расхождение=cut)
                return
            _swap(self, end, grid, warm=False)
            if live:
                door = feed.door
                feed.restart(cut)
                feed.door = door
            journal().mark("сетка по картинке", сегментов=grid.count, было=self._was, заход=cut)

    def _settle(self) -> None:
        self._settled = True
        end = self._end()
        if end is not None and abs(end - self.watch.entry.dur) > SAME_EDGE:
            self._regrid(end)

    def _end(self) -> float | None:
        """Длительность готового паспорта или ``None``, если он не прочитан."""
        try:
            media = self.ahead.result(0)
        except InfraError as exc:
            journal().mark("конец картинки не прочитан", почему=str(exc)[:120])
            return None
        waited = round(_state.CLOCK.monotonic() - self._began, 2)
        journal().mark(
            "конец картинки",
            через=waited,
            после_списка=self._asked,
            длительность=round(media.duration, 3),
        )
        return media.duration

    def _regrid(self, end: float) -> None:
        """До списка кусков: сетка, кодировщик, прогрев и упаковка - по концу ``end``."""
        feed = self.feed
        grid, cut = _layout(self, end)
        slot = feed.door
        while slot < cut and feed.have(slot):
            slot += 1
        if cut <= feed.door or slot >= cut:
            journal().mark("сетка по картинке не встала", дверь=feed.door, расхождение=cut)
            return
        _swap(self, end, grid, warm=not self._warming)
        door = feed.door
        feed.restart(slot)
        feed.door = door
        journal().mark("сетка по картинке", сегментов=grid.count, было=self._was, заход=slot)
