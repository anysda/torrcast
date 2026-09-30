"""Кандидаты одной полки главной из строк ленты, ещё без обложек."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.picture import Picture
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT, fresh_shelf
from torrcast.usecases.shelves.popular_shelf import popular_shelf

__all__ = ["shelf_pictures"]

#: Сколько кандидатов собирается на полку сверх видимых плиток: картины без обложки
#: на полку не попадают, а их места добираются следующими картинами с обложкой
#: (:func:`web.shelf_tiles._covered`), и запас кандидатов - это из чего добирать.
_CANDIDATES: Final = LIMIT * 3


def shelf_pictures(
    shelf: str, rows: list[FeedRow], catalogue: TorrentCatalogue, now: datetime
) -> list[Picture]:
    """Кандидаты полки ``shelf`` с запасом :data:`_CANDIDATES`, ещё без обложек."""
    pick = fresh_shelf if shelf == "fresh" else popular_shelf
    return pick(rows, catalogue, now=now, limit=_CANDIDATES)
