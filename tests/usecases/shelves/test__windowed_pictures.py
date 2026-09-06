"""Проверяет _windowed_pictures: окно по дате, отсев мусора и даты первой раздачи."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.shelves._windowed_pictures import _dates_of, _windowed_pictures

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _row(title: str, info_hash: str, days_ago: int) -> FeedRow:
    return FeedRow(RawResult(title, info_hash, 1000, 5, "rutor"), NOW - timedelta(days=days_ago))


def test_a_raid_outside_the_window_does_not_produce_a_picture() -> None:
    """Раздача старше окна не попадает ни в картины, ни в даты первой раздачи."""
    rows = [_row("Матрица 1999 1080p", "a" * 40, days_ago=20)]

    pictures, dates = _windowed_pictures(rows, torrent_catalogue, days=14, now=NOW)

    assert pictures == []
    assert dates == {}


def test_a_picture_without_a_year_is_dropped() -> None:
    """Без года картину нельзя честно назвать «новинкой» - планка ТЗ §9 требует год."""
    rows = [_row("Какой-то сборник без года", "a" * 40, days_ago=1)]

    pictures, _ = _windowed_pictures(rows, torrent_catalogue, days=14, now=NOW)

    assert pictures == []


def test_a_movie_inside_the_window_produces_one_picture_with_its_date() -> None:
    """Раздача внутри окна кластеризуется в картину, а дата попадает в словарь по хэшу."""
    info_hash = "a" * 40
    rows = [_row("Матрица 1999 1080p", info_hash, days_ago=2)]

    pictures, dates = _windowed_pictures(rows, torrent_catalogue, days=14, now=NOW)

    assert len(pictures) == 1
    assert pictures[0].title == "Матрица"
    assert _dates_of(pictures[0], dates) == [NOW - timedelta(days=2)]


def test_duplicate_hashes_keep_the_earliest_date() -> None:
    """Тот же hash встретился дважды - в словаре остаётся более ранняя раздача."""
    info_hash = "a" * 40
    rows = [
        _row("Матрица 1999 1080p", info_hash, days_ago=1),
        _row("Матрица 1999 1080p", info_hash, days_ago=5),
    ]

    _, dates = _windowed_pictures(rows, torrent_catalogue, days=14, now=NOW)

    assert dates[info_hash] == NOW - timedelta(days=5)
