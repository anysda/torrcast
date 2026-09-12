"""Проверяет fresh_shelf: только 14-дневное окно, самая свежая первая раздача - первой."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.shelves.fresh_shelf import fresh_shelf

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _row(title: str, info_hash: str, days_ago: int) -> FeedRow:
    return FeedRow(RawResult(title, info_hash, 1000, 5, "rutor"), NOW - timedelta(days=days_ago))


def test_a_raid_older_than_fourteen_days_is_excluded() -> None:
    """Окно «Новинок» - 14 суток (ТЗ §9), а не 30, которыми считает «Популярное»."""
    rows = [_row("Старый Фильм 2020 1080p", "a" * 40, days_ago=20)]

    assert fresh_shelf(rows, torrent_catalogue, now=NOW) == []


def test_the_most_recently_raided_picture_comes_first() -> None:
    """Свежую раздачу (1 день назад) показываем раньше более старой (10 дней назад)."""
    rows = [
        _row("Старый Фильм 2026 1080p", "a" * 40, days_ago=10),
        _row("Новый Фильм 2026 1080p", "b" * 40, days_ago=1),
    ]

    shelf = fresh_shelf(rows, torrent_catalogue, now=NOW)

    assert [p.title for p in shelf] == ["Новый Фильм", "Старый Фильм"]


def test_a_recent_reissue_of_an_old_picture_is_not_new() -> None:
    """Новизна полки - год картины сейчас, а не дата её очередной раздачи."""
    rows = [
        _row("Старый Фильм 2020 1080p", "a" * 40, days_ago=1),
        _row("Новый Фильм 2026 1080p", "b" * 40, days_ago=2),
    ]

    shelf = fresh_shelf(rows, torrent_catalogue, now=NOW)

    assert [picture.year for picture in shelf] == [NOW.year]


def test_the_limit_caps_the_shelf() -> None:
    """Плиток не больше запрошенного предела, даже если картин в окне больше."""
    rows = [_row(f"Фильм Номер {i} 2026 1080p", f"{i:040x}", days_ago=1) for i in range(1, 6)]

    shelf = fresh_shelf(rows, torrent_catalogue, now=NOW, limit=3)

    assert len(shelf) == 3
