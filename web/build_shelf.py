"""Плитки одной полки главной из строк ленты: кандидаты, обложки, приговор играбельности."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT, fresh_shelf
from torrcast.usecases.shelves.popular_shelf import popular_shelf
from web.shelf_tiles import Offer, PassportOf, Playable, shelf_tiles

#: Сколько кандидатов собирается на полку сверх видимых плиток: картины без обложки
#: на полку не попадают, а их места добираются следующими картинами с обложкой
#: (:func:`web.shelf_tiles._covered`), и запас кандидатов - это из чего добирать.
_CANDIDATES: Final = LIMIT * 3


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
    pick = fresh_shelf if shelf == "fresh" else popular_shelf
    pictures = pick(rows, catalogue, now=now, limit=_CANDIDATES)
    return shelf_tiles(pictures, offer, passport, playable, limit=LIMIT)


__all__ = ["build_shelf"]
