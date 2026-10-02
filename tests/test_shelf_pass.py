"""Проверяет холодный заход полок: плитки видны до приговоров, «не играет» сходит следом."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.feed_rows import FeedRows
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from torrcast.domain.raw_result import RawResult
from web.built_by_rule import FIELD, RULE
from web.shelf_pass import FILL_BY, SHELVES, SILENT_BY, ShelfPass
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


def test_a_shelf_without_a_single_cover_waits_out_the_silence(tmp_path: Path) -> None:
    """Шторм 429 дольше ``FILL_BY``: ни одна обложка не легла, и полка ждёт, а не заглушки.

    Заход закрывал обе полки плитками без обложек и гасил счётчик; обложки легли бы
    только следующим часом (живой шторм 15 с: 56 плиток, 0 картинок до конца замера).
    """
    cache = _cache(tmp_path, 3)
    cache.landed = lambda records: records
    cache.arriving = lambda _records: True
    shown = ShelfPass(cache, _rows(3), _MOMENT, {})
    shown.pictures = {s: shelf_pictures(s, shown.rows, torrent_catalogue, _MOMENT) for s in SHELVES}
    seeds = {s: shelf_seeds(shown.pictures[s]) for s in SHELVES}
    shown._joint, shown._fresh = seeds["fresh"] + seeds["popular"], len(seeds["fresh"])
    shown._lanes()

    shown._deadline = time.monotonic() - 1
    assert shown._growing()
    assert shown.filling()

    shown._deadline = time.monotonic() - (SILENT_BY - FILL_BY) - 1
    assert not shown._growing()


def test_a_late_feed_does_not_push_the_cold_pass_past_the_budget_from_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Лента пришла поздно: обложки ждут до бюджета от старта процесса, а не срок от вопроса.

    Замер 01-10-2026: вопрос на 4.7 с, срок от него - 29.7 с, счётчик погас на 30.9 с.
    """
    monkeypatch.setattr("web.fill_deadline.FILL_BY", 3.0)
    monkeypatch.setattr("web.fill_deadline.FILL_AT_LEAST", 0.2)
    cache = _cache(tmp_path, 3)
    cache.arriving = lambda _records: True  # some cover is always still on its way
    cache.playable = lambda _query, _key: True
    cache.born = time.monotonic() - 2.9  # the budget ends 0.1 s from now, the ask's 3 s
    began = time.monotonic()

    ShelfPass(cache, _rows(3), _MOMENT, {}).run()

    assert time.monotonic() - began < 2.0
    assert not cache.filling


def test_an_ask_at_the_edge_of_the_budget_still_waits_for_its_covers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Вопрос пришёл к концу бюджета: заход ждёт ``FILL_AT_LEAST``, а не остаток окна.

    Остаток в полсекунды закрывал полку тонкой, а тёплый заход дорастил её после «готово».
    """
    monkeypatch.setattr("web.fill_deadline.FILL_BY", 1.0)
    monkeypatch.setattr("web.fill_deadline.FILL_AT_LEAST", 1.0)
    cache = _cache(tmp_path, 3)
    cache.arriving = lambda _records: True
    cache.playable = lambda _query, _key: True
    cache.born = time.monotonic() - 0.9
    began = time.monotonic()

    ShelfPass(cache, _rows(3), _MOMENT, {}).run()

    assert time.monotonic() - began >= 1.0
    assert not cache.filling


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


def _refill(tmp_path: Path, missed: int) -> tuple[ShelvesCache, list[tuple[bool, bool]]]:
    """Первый заход приносит одну картину, второй - дюжину (m-b3: полка 1+1, потом 24+30)."""
    cache, calls = _cache(tmp_path, 1), [0]

    def feed(_limit: int) -> list[FeedRow]:
        calls[0] += 1
        return FeedRows(_rows(1 if calls[0] == 1 else 12), missed if calls[0] == 1 else 0)

    seen: list[tuple[bool, bool]] = []
    cache.feed, cache.attempts = feed, 2
    cache.sleep = lambda _pause: seen.append((cache.filling, cache.settling))
    later: list[bool] = []  # the fuller attempt is a warm one: its own pass must not put it out

    def playable(_query: str, _key: str) -> bool:
        if calls[0] == 2:
            later.append(cache.filling)
        return True

    cache.playable = playable
    cache._rebuild()
    return cache, [*seen, (all(later), any(later))]


def test_the_counter_stays_on_while_a_fuller_attempt_is_coming(tmp_path: Path) -> None:
    """Лента недосчитала индексер: полка 1+1 - не «готово», счётчик горит через паузу добора."""
    cache, seen = _refill(tmp_path, missed=1)

    assert seen == [(True, True), (True, True)]
    assert len(_titles(cache._body, "fresh")) > 1
    assert not cache.filling and not cache.settling  # the last attempt puts it out


def test_a_whole_feed_puts_the_counter_out_without_waiting_for_the_refill(
    tmp_path: Path,
) -> None:
    """Ответили все индексеры: полнее не будет, счётчик гаснет сразу, а не через паузу."""
    seen = _refill(tmp_path, missed=0)[1]

    assert seen == [(False, False), (False, False)]


@pytest.mark.machine
@pytest.mark.parametrize("edge", [FILL_BY - 0.5, 1e6])
def test_a_cold_ask_at_the_window_edge_does_not_grow_the_shelf_after_ready(
    tmp_path: Path, edge: float
) -> None:
    """Проба мержера: первый заход - отказ каталога, второй спрашивает на краю окна.

    Остаток окна в полсекунды закрывал полку на 3 плитках «Нового», счётчик гас, и
    следующий заход дорастил её до 6 уже после «готово».
    """
    cache = _cache(tmp_path, 6)
    cache.attempts = 3
    late = [0.0]
    calls: list[int] = []

    def feed(_limit: int) -> FeedRows:
        calls.append(1)
        if len(calls) == 1:
            raise InfraError("prowlarr not up yet")
        if len(calls) == 2:
            cache.born = time.monotonic() - edge  # this ask lands `edge` s after the start
            late[0] = time.monotonic() + 2.0
        return FeedRows(_rows(6), missed=0)

    def cover(records: list[JsonValue]) -> list[JsonValue]:
        now = time.monotonic()
        return [
            {**r, "poster": "p"}
            if isinstance(r, dict) and (i % 2 == 0 or now >= late[0] - 0.7)
            else r
            for i, r in enumerate(records)
        ]

    seen: list[tuple[bool, int]] = []

    def sleep(_pause: float) -> None:
        if len(calls) >= 2:
            time.sleep(2.5)
        fresh = cache._body.get("fresh") if cache._body else None
        seen.append((cache.filling, len(_titles(cache._body, "fresh")) if fresh else 0))

    cache.feed = feed
    cache.ask = cover
    cache.landed = cover
    cache.offer = cover
    cache.arriving = lambda _records: time.monotonic() < late[0]
    cache.playable = lambda _query, _key: True
    cache.sleep = sleep
    cache._rebuild()
    seen.append((cache.filling, len(_titles(cache._body, "fresh"))))

    grew_after_ready = any(not on and n < seen[-1][1] for on, n in seen[1:-1])
    assert not grew_after_ready, f"shelf grew after the counter went out: {seen}"
