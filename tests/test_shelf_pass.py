"""Проверяет холодный заход полок: плитки видны до приговоров, «не играет» сходит следом."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.raw_result import RawResult
from web.built_by_rule import FIELD, RULE
from web.shelf_pass import SHELVES, ShelfPass
from web.shelf_pictures import shelf_pictures
from web.shelf_seeds import shelf_seeds
from web.shelves_cache import ShelvesCache

_MOMENT = datetime(2026, 9, 30, tzinfo=UTC)


def _rows(count: int) -> list[FeedRow]:
    return [
        FeedRow(
            RawResult(f"Картина {index:02d} 2026 1080p", f"{index:040x}", 1000, 5, "rutor"),
            datetime(2026, 9, 29, tzinfo=UTC),
        )
        for index in range(count)
    ]


def _covered(records: list[JsonValue]) -> list[JsonValue]:
    return [{**record, "poster": "p"} if isinstance(record, dict) else record for record in records]


def _cache(tmp_path: Path, count: int, *, early: bool = True) -> ShelvesCache:
    return ShelvesCache(
        feed=lambda _limit: _rows(count),
        catalogue=torrent_catalogue,
        offer=_covered,  # the warm path waits for the bytes; the cold one asks and moves on
        path=tmp_path / "shelves.json",
        attempts=1,
        sleep=lambda _pause: None,
        passport=lambda title, series, timeout: Origin(),
        spawn=lambda job: None,
        clock=lambda: _MOMENT,
        ask=_covered,
        landed=_covered,
        early=early,
        workers=2,
    )


def _titles(body: dict[str, JsonValue] | None, shelf: str) -> list[str]:
    assert body is not None
    tiles = body[shelf]
    assert isinstance(tiles, list)
    return [str(tile.get("title")) for tile in tiles if isinstance(tile, dict)]


def test_a_cold_shelf_is_shown_before_its_first_verdict(tmp_path: Path) -> None:
    """Первый приговор ещё не вынесен, а обе полки уже на экране - и без клейма правила."""
    cache = _cache(tmp_path, 3)
    seen: list[tuple[dict[str, JsonValue] | None, bool]] = []

    def playable(_query: str, _key: str) -> bool:
        seen.append((cache._body, cache.settling))
        return True

    cache.playable = playable
    cache._rebuild()

    first, settling = seen[0]
    assert len(_titles(first, "fresh")) == 3
    assert len(_titles(first, "popular")) == 3
    assert first is not None and FIELD not in first
    assert settling
    assert cache._body is not None and cache._body[FIELD] == RULE
    assert not cache.settling and not cache.filling


def test_a_tile_that_does_not_play_leaves_the_shown_shelf(tmp_path: Path) -> None:
    """Показанная до приговора плитка сходит, как только её «не играет» вынесено."""
    cache = _cache(tmp_path, 3)
    cache.playable = lambda _query, key: key != "movie:картина-01:2026"
    before = cache._load()
    assert before["built_at"] is None

    cache._rebuild()

    assert "Картина 01" not in " ".join(_titles(cache._body, "fresh"))
    assert len(_titles(cache._body, "fresh")) == 2


def test_an_unknown_verdict_keeps_the_shown_tile(tmp_path: Path) -> None:
    """Сеть легла - «не знаю»: плитка остаётся, отказ стенда не приговор картине."""
    cache = _cache(tmp_path, 3)
    cache.playable = lambda _query, _key: None

    cache._rebuild()

    assert len(_titles(cache._body, "fresh")) == 3


def test_a_shelf_built_by_this_rule_is_not_replaced_by_an_unjudged_one(tmp_path: Path) -> None:
    """Тёплый заход ничего не показывает до приговоров: на экране уже проверенная полка."""
    cache = _cache(tmp_path, 3)
    cache._rebuild()
    shown: list[dict[str, JsonValue] | None] = []

    def playable(_query: str, _key: str) -> bool:
        shown.append(cache._body)
        return True

    cache.playable = playable
    cache._rebuild()

    assert shown
    assert all(body is not None and body.get(FIELD) == RULE for body in shown)


def test_the_cold_page_stays_partial_until_the_shelves_are_shown(tmp_path: Path) -> None:
    """До первого показа счётчик страницы горит, хотя тело на диске ещё пусто."""
    cache = _cache(tmp_path, 2)
    flags: list[bool] = []
    ask = cache.ask
    assert ask is not None

    def asking(records: list[JsonValue]) -> list[JsonValue]:
        flags.append(cache.filling)
        return ask(records)

    cache.ask = asking
    cache._rebuild()

    assert flags == [True]
    assert not cache.filling


def test_the_preview_hides_a_tile_judged_unplayable_and_keeps_an_unknown_one(
    tmp_path: Path,
) -> None:
    """Показ до конца приговоров уже не несёт «не играет», а «не знаю» держит на месте."""
    cache = _cache(tmp_path, 3)
    shown = ShelfPass(cache, _rows(3), _MOMENT, {})
    shown.pictures = {s: shelf_pictures(s, shown.rows, torrent_catalogue, _MOMENT) for s in SHELVES}
    shown.looked = {s: _covered(shelf_seeds(shown.pictures[s])) for s in SHELVES}
    shown.verdicts = {"movie:картина-01:2026": False, "movie:картина-02:2026": None}

    shown._preview()

    assert sorted(_titles(cache._body, "fresh")) == ["Картина 00", "Картина 02"]
    assert sorted(_titles(cache._body, "popular")) == ["Картина 00", "Картина 02"]


def test_a_cold_shelf_stops_growing_once_its_counter_is_off(tmp_path: Path) -> None:
    """Счётчик погас - состав застыл: обложка, легшая позже, полку уже не меняет."""
    cache = _cache(tmp_path, 3)
    late: list[str] = []
    cache.landed = lambda records: [
        {**record, "poster": "p"} if isinstance(record, dict) and late else record
        for record in records
    ]
    cache.arriving = lambda _records: True
    shown = ShelfPass(cache, _rows(3), _MOMENT, {})
    shown.pictures = {s: shelf_pictures(s, shown.rows, torrent_catalogue, _MOMENT) for s in SHELVES}
    seeds = {s: shelf_seeds(shown.pictures[s]) for s in SHELVES}
    shown._joint, shown._fresh = seeds["fresh"] + seeds["popular"], len(seeds["fresh"])
    shown._deadline = time.monotonic() + 60

    late.append("p")
    shown._lanes()
    assert shown._growing()
    assert all("poster" in tile for tile in shown.looked["fresh"] if isinstance(tile, dict))

    late.clear()
    shown._deadline = time.monotonic() - 1
    assert not shown._growing()
    late.append("p")
    before = shown.looked
    shown._lanes()
    assert shown.looked is before


def test_a_saved_shelf_missing_one_row_is_rebuilt_as_cold(tmp_path: Path) -> None:
    """Тело этого правила без одной полки не тёплое: пустая полка встаёт до приговоров.

    Такое тело оставляет прежняя сборка, опубликовавшая одну полку и не дошедшая до
    второй: выкатка поверх него держала «Популярное» пустым до конца приговоров.
    """
    cache = _cache(tmp_path, 3)
    cache._rebuild()
    assert cache._body is not None
    cache._body = {**cache._body, "popular": []}
    seen: list[list[str]] = []

    def playable(_query: str, _key: str) -> bool:
        seen.append(_titles(cache._body, "popular"))
        return True

    cache.playable = playable
    cache._rebuild()

    assert len(seen[0]) == 3
    assert cache._body is not None and cache._body[FIELD] == RULE
    assert len(_titles(cache._body, "popular")) == 3
