"""Полка «Популярное»: те же картины за 30 дней, впереди - у кого больше сидов суммой."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.picture import Picture
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves._windowed_pictures import _windowed_pictures

#: Окно ленты «Популярное» в сутках (ТЗ §9).
DAYS: Final = 30
#: Видимых плиток на полке (ТЗ §9).
LIMIT: Final = 30


def popular_shelf(
    rows: list[FeedRow],
    catalogue: TorrentCatalogue,
    *,
    now: datetime | None = None,
    limit: int = LIMIT,
) -> list[Picture]:
    """Картины 30-дневного окна ленты по сумме сидов всех её раздач.

    :attr:`torrcast.domain.picture.Picture.seeders` тут не годится - он берёт максимум
    ОДНОЙ раздачи, а полке нужен интерес зрителей ко всей картине: у пяти слабых раздач
    в сумме может быть больше сидов, чем у одной сильной.
    """
    moment = now or datetime.now(UTC)
    pictures, _ = _windowed_pictures(rows, catalogue, days=DAYS, now=moment)
    pictures.sort(key=lambda picture: sum(r.seeders for r in picture.releases), reverse=True)
    return pictures[:limit]


__all__ = ["DAYS", "LIMIT", "popular_shelf"]
