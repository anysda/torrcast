"""Сетка показа по концу картинки: раскладка, расхождение с нынешней и замена участников.

Зовёт его только конец картинки (:class:`torrcast.usecases.playback._ending._Ending`).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Final, Protocol

from torrcast.usecases.feed_pack.feed_segment import _stocked
from torrcast.usecases.playback._cuttable import _Cuttable
from torrcast.usecases.playback._relabel import _Relabel

if TYPE_CHECKING:
    from torrcast.ports.feed_grid import FeedGrid
    from torrcast.ports.receiver import Receiver
    from torrcast.ports.recode.encoding import Encoding
    from torrcast.ports.recode.spot_recoder import SpotRecoder
    from torrcast.ports.stream_source import StreamSource
    from torrcast.usecases.playback.ended_feed import EndedFeed
    from torrcast.usecases.playback.media_grid import MediaGrid
    from torrcast.usecases.playback.stream_server import StreamServer
    from torrcast.usecases.warm.warmer import Warmer
    from torrcast.usecases.watch import Watch

#: Насколько границы куска могут разойтись, оставаясь той же границей.
SAME_EDGE: Final = 1e-6


class _Ending(Protocol):
    """Чем конец картинки делится со сменой сетки (сам он - ``_ending._Ending``)."""

    recoder: SpotRecoder | None
    warmer: Warmer | None
    _was: int

    @property
    def watch(self) -> Watch: ...
    @property
    def supply(self) -> StreamSource | None: ...
    @property
    def relayout(self) -> Callable[[], tuple[MediaGrid, Encoding | None]]: ...
    @property
    def rebuild(self) -> Callable[..., tuple[SpotRecoder | None, Warmer | None]]: ...
    @property
    def feed(self) -> EndedFeed: ...
    @property
    def server(self) -> StreamServer: ...
    @property
    def receiver(self) -> Receiver: ...
    @property
    def start(self) -> float: ...


def _layout(ending: _Ending, end: float) -> tuple[MediaGrid, int]:
    """Сетка по концу ``end`` и первый кусок, где она расходится с нынешней."""
    entry = ending.watch.entry
    was, entry.dur = entry.dur, end
    try:
        grid = ending.relayout()[0]
    finally:
        entry.dur = was
    return grid, _first_change(ending.feed.grid, grid)


def _swap(ending: _Ending, end: float, grid: MediaGrid, *, warm: bool) -> None:
    """Запись, источник, кодировщик и сетка ленты - по концу ``end``; прогрев - если ``warm``.

    Прогрев, уже отданный показу (``warm=False``), остаётся прежним: его куски сверяются с
    сеткой ленты при выдаче (:func:`torrcast.usecases.feed_pack.feed_segment._warm`), а
    кодировщик живых кусков он только сторожится (:attr:`Warmer.rival`).
    """
    feed = ending.feed
    ending._was = feed.grid.count
    ending.watch.entry.dur = end
    if ending.supply is not None:
        ending.supply.duration = end
    recoder, warmer = ending.rebuild(grid=grid, warm=warm)
    if ending.recoder is not None:
        ending.recoder.stop()
    feed.grid, feed.recoder = grid, recoder
    if warm:
        feed.vault = None if warmer is None else warmer.vault
        if isinstance(ending.server, _Relabel):
            ending.server.relabel(set() if warmer is None else warmer.vault.served)
        ending.warmer = warmer
    elif ending.warmer is not None:
        ending.warmer.rival = recoder
    if recoder is not None:
        recoder.stock(partial(_stocked, feed))
        recoder.played = max(ending.start, feed.played)
        recoder.start()
    if isinstance(ending.receiver, _Cuttable):
        ending.receiver.next_cut = grid.after
    ending.recoder = recoder


def _first_change(old: FeedGrid, new: FeedGrid) -> int:
    """Первый кусок, чьи границы у двух сеток расходятся."""
    for slot in range(min(old.count, new.count)):
        if abs(old.start(slot) - new.start(slot)) > SAME_EDGE:
            return slot
        if abs(old.end(slot) - new.end(slot)) > SAME_EDGE:
            return slot
    return min(old.count, new.count)
