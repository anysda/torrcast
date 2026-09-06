"""Проверяет ShelvesCache: полки строятся фоном, читаются мгновенно, сеть - не в GET."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from torrcast.domain.raw_result import RawResult
from web.shelves_cache import Feed, Offer, ShelvesCache, Spawn

_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)


def _rows() -> list[FeedRow]:
    return [
        FeedRow(
            RawResult("Матрица 1999 1080p", "a" * 40, 1000, 5, "rutor"),
            datetime(2026, 9, 5, tzinfo=UTC),
        )
    ]


def _cache(
    tmp_path: Path,
    *,
    feed: Feed | None = None,
    offer: Offer | None = None,
    spawn: Spawn | None = None,
) -> ShelvesCache:
    return ShelvesCache(
        feed=feed or (lambda limit: _rows()),
        catalogue=torrent_catalogue,
        offer=offer or (lambda records: records),
        path=tmp_path / "shelves.json",
        spawn=spawn or (lambda job: None),
        clock=lambda: _MOMENT,
    )


def _tile(shelf: JsonValue, index: int) -> dict[str, JsonValue]:
    """Плитка полки с проверенным типом - тесты читают её поля без гаданий mypy."""
    assert isinstance(shelf, list)
    tile = shelf[index]
    assert isinstance(tile, dict)
    return tile


def test_before_the_first_build_the_shelves_are_empty_not_blocking(tmp_path: Path) -> None:
    """Фон ещё не бегал и диска нет - полки честно пусты, а не выдуманы."""
    body = _cache(tmp_path).get()

    assert body == {"fresh": [], "popular": [], "built_at": None}


def test_rebuild_fills_both_shelves_with_projected_tiles(tmp_path: Path) -> None:
    """После сборки плитка несёт ровно контрактные поля ``/api/shelves``, и ни одного лишнего."""
    cache = _cache(tmp_path)

    cache._rebuild()

    body = cache._body
    assert body is not None
    assert body["built_at"] == "2026-09-06T00:00:00+00:00"
    fresh = body["fresh"]
    assert isinstance(fresh, list)
    assert len(fresh) == 1
    tile = _tile(fresh, 0)
    assert set(tile) == {"key", "title", "year", "kind", "quality", "poster", "query"}
    assert tile["title"] == "Матрица"


def test_rebuild_persists_the_cache_and_a_fresh_instance_reads_it_back(tmp_path: Path) -> None:
    """Кэш переживает рестарт службы: новый предмет находит собранное на диске."""
    path = tmp_path / "shelves.json"
    built = ShelvesCache(
        feed=lambda limit: _rows(),
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=path,
        spawn=lambda job: None,
        clock=lambda: _MOMENT,
    )
    built._rebuild()

    assert path.exists()
    reread = ShelvesCache(
        feed=lambda limit: [],
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=path,
        spawn=lambda job: None,
    )

    assert _tile(reread.get()["fresh"], 0)["title"] == "Матрица"


def test_offer_is_the_only_place_a_poster_field_can_come_from(tmp_path: Path) -> None:
    """Обложку дописывает переданный ``offer``, как у выдачи поиска - своего пути тут нет."""
    seen: list[list[JsonValue]] = []

    def fake_offer(records: list[JsonValue]) -> list[JsonValue]:
        seen.append(records)
        return [{**r, "poster": "abc"} if isinstance(r, dict) else r for r in records]

    cache = _cache(tmp_path, offer=fake_offer)

    cache._rebuild()

    body = cache._body
    assert body is not None
    assert _tile(body["fresh"], 0)["poster"] == "abc"
    assert seen, "offer обязан был увидеть плитки перед сборкой ответа"


def test_a_broken_feed_does_not_crash_the_rebuild(tmp_path: Path) -> None:
    """Отказ ленты (Prowlarr лёг) не роняет фон - просто не обновляет полки в этот раз."""

    def failing_feed(limit: int) -> list[FeedRow]:
        raise InfraError("прибили")

    cache = _cache(tmp_path, feed=failing_feed)

    cache._rebuild()  # не должно бросить наружу

    assert cache._body is None


def test_get_starts_the_background_loop_exactly_once(tmp_path: Path) -> None:
    """Фон встаёт при первом обращении и только при нём - не при каждом запросе."""
    calls: list[object] = []
    cache = _cache(tmp_path, spawn=lambda job: calls.append(job))

    cache.get()
    cache.get()
    cache.get()

    assert len(calls) == 1


def test_the_loop_rebuilds_then_sleeps_for_the_configured_period(tmp_path: Path) -> None:
    """Цикл фона: сборка, потом сон на ``every`` секунд, и так по кругу."""
    build_count = 0

    def counting_feed(limit: int) -> list[FeedRow]:
        nonlocal build_count
        build_count += 1
        return []

    slept: list[float] = []

    def stopping_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise RuntimeError("stop the loop for the test")

    cache = ShelvesCache(
        feed=counting_feed,
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=tmp_path / "shelves.json",
        spawn=lambda job: None,
        sleep=stopping_sleep,
        every=3600.0,
    )

    with pytest.raises(RuntimeError, match="stop the loop"):
        cache._loop()

    assert build_count == 1
    assert slept == [3600.0]
