"""Полка «Новинки»: раздачи ленты за 14 дней, самая свежая первая раздача - первой."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from torrcast.domain.feed_row import FeedRow
from torrcast.domain.picture import Picture
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves._windowed_pictures import _dates_of, _windowed_pictures

#: Окно ленты «Новинки» в сутках (ТЗ §9).
DAYS: Final = 14
#: Видимых плиток на полке (ТЗ §9).
LIMIT: Final = 30


def fresh_shelf(
    rows: list[FeedRow],
    catalogue: TorrentCatalogue,
    *,
    now: datetime | None = None,
    limit: int = LIMIT,
) -> list[Picture]:
    """Картины 14-дневного окна ленты, отсортированные по дате первой раздачи.

    «Первая раздача» - минимум дат её релизов внутри окна, а не максимум: считаем, КОГДА
    картина впервые появилась в ленте, а не когда её раздали заново. Впереди списка -
    самая недавняя из этих дат: она и есть самая настоящая новинка.
    """
    moment = now or datetime.now(UTC)
    pictures, dates = _windowed_pictures(rows, catalogue, days=DAYS, now=moment)
    pictures = [picture for picture in pictures if picture.year == moment.year]

    def _first_raid(picture: Picture) -> datetime:
        found = _dates_of(picture, dates)
        return min(found) if found else datetime.min.replace(tzinfo=UTC)

    pictures.sort(key=_first_raid, reverse=True)
    return pictures[:limit]


__all__ = ["DAYS", "LIMIT", "fresh_shelf"]
