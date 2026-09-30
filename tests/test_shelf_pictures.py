"""Проверяет shelf_pictures: кандидаты полки берутся с запасом против видимых плиток."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.shelves.fresh_shelf import LIMIT
from web.shelf_pictures import shelf_pictures

_MOMENT = datetime(2026, 9, 30, tzinfo=UTC)


def _rows(count: int) -> list[FeedRow]:
    return [
        FeedRow(
            RawResult(f"Картина {index:03d} 2026 1080p", f"{index:040x}", 1000, index, "rutor"),
            datetime(2026, 9, 29, tzinfo=UTC),
        )
        for index in range(count)
    ]


def test_a_shelf_takes_three_times_its_visible_tiles_as_candidates() -> None:
    """Место картины без обложки добирается из запаса: кандидатов втрое больше плиток."""
    for shelf in ("fresh", "popular"):
        assert len(shelf_pictures(shelf, _rows(LIMIT * 4), torrent_catalogue, _MOMENT)) == LIMIT * 3


def test_the_popular_shelf_puts_the_most_seeded_picture_first() -> None:
    """«Популярное» - отбор по сидам, а кандидаты у обеих полок из одной ленты."""
    rows = _rows(5)
    fresh = [p.title for p in shelf_pictures("fresh", rows, torrent_catalogue, _MOMENT)]
    popular = [p.title for p in shelf_pictures("popular", rows, torrent_catalogue, _MOMENT)]

    assert popular[0] == "Картина 004"
    assert sorted(fresh) == sorted(popular)
