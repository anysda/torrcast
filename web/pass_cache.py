"""Что заход полок (:class:`web.shelf_pass.ShelfPass`) берёт у кэша полок.

Кэш - :class:`web.shelves_cache.ShelvesCache`; он сам строит заходы, и прямой импорт
замкнул бы цикл модулей.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol, runtime_checkable

from torrcast.domain.json_value import JsonValue
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from web.drop_count import DropCount
from web.shelf_tiles import Offer, PassportOf, Playable


@runtime_checkable
class PassCache(Protocol):
    """Что заход берёт у :class:`web.shelves_cache.ShelvesCache` (без цикла импортов)."""

    filling: bool
    settling: bool
    born: float  # when the process started: the cover wait counts from it

    @property
    def catalogue(self) -> TorrentCatalogue: ...
    @property
    def offer(self) -> Offer: ...
    @property
    def ask(self) -> Offer | None: ...
    @property
    def landed(self) -> Offer: ...
    @property
    def arriving(self) -> Callable[[list[JsonValue]], bool]: ...
    @property
    def passport(self) -> PassportOf: ...
    @property
    def playable(self) -> Playable: ...
    @property
    def workers(self) -> int: ...
    @property
    def early(self) -> bool: ...
    def publish(
        self,
        shelf: str,
        tiles: list[JsonValue],
        drops: DropCount,
        now: datetime,
        complete: bool,
        unstamped: bool = False,
    ) -> None: ...


__all__ = ["PassCache"]
