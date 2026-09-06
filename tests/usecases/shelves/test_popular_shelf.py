"""Проверяет popular_shelf: 30-дневное окно, сортировка по сумме сидов, а не по максимуму."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.shelves.popular_shelf import popular_shelf

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _row(title: str, info_hash: str, seeders: int, days_ago: int) -> FeedRow:
    return FeedRow(
        RawResult(title, info_hash, 1000, seeders, "rutor"), NOW - timedelta(days=days_ago)
    )


def test_a_raid_older_than_thirty_days_is_excluded() -> None:
    """Окно «Популярного» - 30 суток (ТЗ §9), а не 14, которыми считают «Новинки»."""
    rows = [_row("Старый Фильм 2020 1080p", "a" * 40, 100, days_ago=31)]

    assert popular_shelf(rows, torrent_catalogue, now=NOW) == []


def test_sorting_is_by_the_sum_of_seeders_not_by_a_single_release() -> None:
    """Пять слабых раздач одной картины суммой сидов обходят одну сильную раздачу другой."""
    rows = [
        _row("Одна Сильная 2026 1080p", "a" * 40, 100, days_ago=1),
        *(_row("Пять Слабых 2026 1080p", f"{i:040x}", 30, days_ago=1) for i in range(1, 6)),
    ]

    shelf = popular_shelf(rows, torrent_catalogue, now=NOW)

    assert [p.title for p in shelf] == ["Пять Слабых", "Одна Сильная"]


def test_the_limit_caps_the_shelf() -> None:
    rows = [_row(f"Фильм Номер {i} 2026 1080p", f"{i:040x}", 1, days_ago=1) for i in range(1, 6)]

    shelf = popular_shelf(rows, torrent_catalogue, now=NOW, limit=3)

    assert len(shelf) == 3
