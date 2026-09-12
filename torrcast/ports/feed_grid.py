"""Сетка сегментов в объёме, который нужен подаче потока.

Спрашивают её упаковщик и лента (:mod:`torrcast.usecases.feed_pack`), а строит адаптер.
"""

from collections.abc import Collection
from typing import Protocol

from torrcast.domain.segment_container import MPEGTS, SegmentContainer


class FeedGrid(Protocol):
    """Границы кусков фильма и манифест на весь фильм."""

    @property
    def count(self) -> int: ...
    @property
    def duration(self) -> float: ...
    @property
    def origin(self) -> float: ...

    def start(self, slot: int) -> float: ...
    def end(self, slot: int) -> float: ...
    def span(self, slot: int) -> float: ...
    def slot_at(self, seconds: float) -> int: ...
    #: ``gaps`` - места этого показа, которых не будет: ниже захода упаковки живой кусок не
    #: появится, и обещать его нельзя. Знает их лента, а не сетка: сетка про фильм, а не
    #: про показ (:meth:`torrcast.usecases.feed_pack.feed.Feed._gaps`).
    def manifest(self, container: SegmentContainer = MPEGTS, gaps: Collection[int] = ()) -> str: ...
