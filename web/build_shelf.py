"""Плитки одной полки главной из строк ленты: кандидаты, обложки, приговор играбельности."""

from __future__ import annotations

from datetime import datetime

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT
from web.shelf_pictures import shelf_pictures
from web.shelf_tiles import Offer, PassportOf, Playable, shelf_tiles


def build_shelf(
    shelf: str,
    rows: list[FeedRow],
    catalogue: TorrentCatalogue,
    offer: Offer,
    passport: PassportOf,
    playable: Playable,
    now: datetime,
) -> list[JsonValue]:
    """Видимые плитки полки ``shelf``: только картины с обложкой, в числе видимых ТЗ §9.

    ``playable`` приходит со счётчиком ЭТОЙ полки (:class:`web.drop_count.DropCount`),
    чтобы один заход не мешал свой счёт отсева с чужим.
    """
    return shelf_tiles(
        shelf_pictures(shelf, rows, catalogue, now), offer, passport, playable, LIMIT
    )


__all__ = ["build_shelf"]
