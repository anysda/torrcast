"""Сетка сегментов в объёме, который нужен прогреву."""

from collections.abc import Callable
from typing import Protocol

from torrcast.ports.feed_grid import FeedGrid


class WarmGrid(FeedGrid, Protocol):
    """Границы кусков фильма: где начинается кусок, где кончается и сколько весит.

    Договор ленты (:class:`torrcast.ports.feed_grid.FeedGrid`) входит сюда целиком не для
    полноты: прогрев эту же сетку ОТДАЁТ заходу упаковки, и заход спрашивает у неё своё.
    Сузь её тут - и сужение было бы неправдой ровно на границе, где сетка уходит дальше.
    """

    @property
    def count(self) -> int: ...
    @property
    def duration(self) -> float: ...
    @property
    def origin(self) -> float: ...
    @property
    def on_keys(self) -> bool: ...
    @property
    def weigh(self) -> Callable[[float, float], float] | None: ...

    def start(self, slot: int) -> float: ...
    def end(self, slot: int) -> float: ...
    def span(self, slot: int) -> float: ...
