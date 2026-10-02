"""Проверяет холодный заход полок: плитки видны до приговоров, «не играет» сходит следом."""

from __future__ import annotations

import threading
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
from torrcast.usecases.shelves.fresh_shelf import LIMIT
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


def test_a_shelf_at_its_limit_keeps_the_counter_on_while_covers_still_arrive(
    tmp_path: Path,
) -> None:
    """Полка набрала ``LIMIT`` плиток, а обложки едут: картина выше рангом ещё сменит хвост.

    Замер 02-10-2026: счётчик погас на 16.2 с при 30+30, а на 18.2 и 19.2 с легли обложки
    картин выше по рангу и вытеснили последние плитки - полка сменилась после «готово».
    """
    cache = _cache(tmp_path, 3)
    cache.arriving = lambda _records: True
    shown = ShelfPass(cache, _rows(3), _MOMENT, {})
    shown._joint = [{"title": "Картина 00"}]
    shown._deadline = time.monotonic() + 60
    shown.shown = {shelf: [f"movie:{index}" for index in range(LIMIT)] for shelf in SHELVES}

    assert shown.filling()

    shown._deadline = time.monotonic() - SILENT_BY
    assert not shown.filling()


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


class _StopError(Exception):
    """Конец бесконечного цикла фона в тесте."""


def _short_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer_in: float | None
) -> tuple[ShelvesCache, list[tuple[bool, int]], list[float], float]:
    """Лента недосчитала индексер (m-b3: полка 1+1): переспрос приносит дюжину через
    ``answer_in`` с, ``None`` - молчит до срока. Срок обложек - секунда от вопроса."""
    monkeypatch.setattr("web.fill_deadline.FILL_BY", 0.0)
    monkeypatch.setattr("web.fill_deadline.FILL_AT_LEAST", 1.0)
    cache = _cache(tmp_path, 1)

    def again(within: float) -> FeedRows:
        if answer_in is None or answer_in > within:
            time.sleep(within)
            return FeedRows([], missed=1, again=again)
        time.sleep(answer_in)
        return FeedRows(_rows(12))

    pauses: list[float] = []
    cache.feed, cache.attempts = lambda _limit: FeedRows(_rows(1), missed=1, again=again), 3
    cache.sleep, cache.playable = pauses.append, lambda _query, _key: True
    seen: list[tuple[bool, int]] = []  # (counter before, fresh tiles after) at each publish
    publish = cache.publish

    def watched(shelf: str, tiles: list[JsonValue], *args: object, **kwargs: object) -> None:
        on = cache.filling
        publish(shelf, tiles, *args, **kwargs)  # type: ignore[arg-type]
        body = cache._body or {}
        seen.append((on, len(_titles(body, "fresh")) if body.get("fresh") else 0))

    cache.publish = watched  # type: ignore[method-assign]
    began = time.monotonic()
    cache._rebuild()
    return cache, seen, pauses, time.monotonic() - began


def _grew_after_ready(seen: list[tuple[bool, int]]) -> bool:
    out = [index for index, (on, _tiles) in enumerate(seen) if not on]
    return bool(out) and any(seen[index][1] > seen[out[0] - 1][1] for index in out)


def test_the_counter_stays_on_while_a_fuller_attempt_makes_the_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Недосчитанный индексер ответил к сроку: полка 1+1 - не «готово», дюжина встаёт до него."""
    cache, seen, pauses, _spent = _short_feed(tmp_path, monkeypatch, answer_in=0.3)

    assert seen[0] == (True, 1)
    assert not _grew_after_ready(seen), seen
    assert len(_titles(cache._body, "fresh")) > 1
    assert pauses == []  # no 10 s pause and no second feed of every indexer
    assert not cache.filling and not cache.short


def test_past_the_deadline_a_short_feed_is_ready_even_at_one_and_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сторож: недосчитанный так и молчит - «готово» на сроке при 1+1, пересборка назначена."""
    cache, seen, pauses, spent = _short_feed(tmp_path, monkeypatch, answer_in=None)

    assert spent < 2.0  # the deadline is a second from the ask
    assert not _grew_after_ready(seen), seen
    assert len(_titles(cache._body, "fresh")) == 1
    assert len(_titles(cache._body, "popular")) == 1
    assert pauses == [] and not cache.filling
    assert cache.short


def _next_sleep(cache: ShelvesCache) -> float:
    pauses: list[float] = []

    def sleep(pause: float) -> None:
        pauses.append(pause)
        raise _StopError

    cache.sleep = sleep
    cache._rebuild = lambda: None  # type: ignore[method-assign]
    with pytest.raises(_StopError):
        cache._loop()
    return pauses[0]


def test_a_shelf_still_short_at_the_deadline_is_rebuilt_in_minutes_not_an_hour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Тонкая полка не висит час: новая пересборка через ``soon``, не раньше пяти минут."""
    cache = _short_feed(tmp_path, monkeypatch, answer_in=None)[0]

    assert cache.soon >= 300.0
    assert _next_sleep(cache) == cache.soon


def test_a_whole_feed_puts_the_counter_out_and_waits_the_hour(tmp_path: Path) -> None:
    """Ответили все индексеры: добирать нечего, счётчик гаснет, следующая сборка через час."""
    cache = _cache(tmp_path, 3)
    cache.feed = lambda _limit: FeedRows(_rows(3))
    cache.attempts = 3
    cache._rebuild()

    assert not cache.filling and not cache.short
    assert _next_sleep(cache) == cache.every


def test_an_indexer_short_on_every_pass_stops_the_early_rebuilds_after_two(
    tmp_path: Path,
) -> None:
    """Вечно опаздывающий индексер: две ранние пересборки подряд, дальше обычный час, а
    проход с целой лентой снова даёт недосчёту раннюю пересборку."""
    cache = _cache(tmp_path, 3)
    shorts = iter([True, True, True, True, False, True])
    pauses: list[float] = []

    def rebuild() -> None:
        cache.short = next(shorts)

    def sleep(pause: float) -> None:
        pauses.append(pause)
        if len(pauses) == 6:
            raise _StopError

    cache._rebuild = rebuild  # type: ignore[method-assign]
    cache.sleep = sleep
    with pytest.raises(_StopError):
        cache._loop()

    soon, hour = cache.soon, cache.every
    assert pauses == [soon, soon, hour, hour, hour, soon]


def _rebuild_under_the_page(cache: ShelvesCache) -> list[tuple[bool, dict[str, set[str]]]]:
    """Пересборка глазами страницы: опрос ``X-Torrcast-Partial`` и плиток каждые 5 мс.

    Страница гасит счётчик, когда у тела есть ``built_at`` и ``filling`` погас
    (:mod:`web.shelves`); «готово» - первый такой опрос с непустым «Новым».
    """
    polls: list[tuple[bool, dict[str, set[str]]]] = []
    stop = threading.Event()

    def page() -> None:
        while not stop.is_set():
            body = cache._body or {}
            partial = body.get("built_at") is None or cache.filling
            keys: dict[str, set[str]] = {}
            for shelf in SHELVES:
                tiles = body.get(shelf)
                tiles = tiles if isinstance(tiles, list) else []
                keys[shelf] = {str(t.get("key")) for t in tiles if isinstance(t, dict)}
            polls.append((partial, keys))
            time.sleep(0.005)

    poller = threading.Thread(target=page)
    poller.start()
    try:
        cache._rebuild()
        time.sleep(0.05)
    finally:
        stop.set()
        poller.join()
    return polls


def _ready(polls: list[tuple[bool, dict[str, set[str]]]]) -> int:
    ready = next(
        (i for i, (partial, keys) in enumerate(polls) if not partial and keys["fresh"]), None
    )
    assert ready is not None, polls[-3:]
    return ready


@pytest.mark.machine
@pytest.mark.parametrize("edge", [FILL_BY - 0.5, 1e6])
def test_a_cold_ask_at_the_window_edge_is_whole_at_ready_and_does_not_grow(
    tmp_path: Path, edge: float
) -> None:
    """Проба мержера: первый заход - отказ каталога, второй спрашивает на краю окна.

    Половина обложек приходит сразу, вторая - через 1.3 с после вопроса. Остаток окна
    в полсекунды закрывал полку на 3 плитках «Нового» из 6: страница видела «готово»
    на тонкой полке. Здесь в миг «готово» полка целая, и после него не растёт.
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

    cache.feed = feed
    cache.ask = cache.landed = cache.offer = cover
    cache.arriving = lambda _records: time.monotonic() < late[0]
    cache.playable = lambda _query, _key: True
    cache.filling = True  # what start() sets for a cold body
    polls = _rebuild_under_the_page(cache)

    ready = _ready(polls)
    at_ready = polls[ready][1]
    grew = {k for _p, keys in polls[ready:] for s in SHELVES for k in keys[s] - at_ready[s]}
    assert len(at_ready["fresh"]) == 6, f"thin «ready»: {len(at_ready['fresh'])} of 6"
    assert not grew, f"grew after ready: {sorted(grew)}"


@pytest.mark.machine
def test_a_verdict_after_ready_does_not_let_an_old_rule_tile_in(tmp_path: Path) -> None:
    """Проба мержера: тело на диске собрано прежним правилом (подъём ``RULE`` или рестарт
    посреди холодного захода). «Не играет» после «готово» снимает плитку, и прежде на её
    место вставала старая плитка, которой страница не видела."""
    cache = _cache(tmp_path, 5)
    old: dict[str, JsonValue] = {
        shelf: [
            {"key": f"movie:старая-{shelf}-{i:02d}:2020", "title": f"Старая {i:02d}"}
            for i in range(LIMIT)
        ]
        for shelf in SHELVES
    }
    cache._body = {**old, "built_at": "2026-09-29T00:00:00+00:00", FIELD: RULE - 1}
    dropped = "movie:картина-00:2026"

    def playable(_query: str, key: str) -> bool:
        time.sleep(0.05)  # verdicts come after the covers, as on the stand
        return key != dropped

    cache.playable = playable
    cache.filling = True
    polls = _rebuild_under_the_page(cache)

    ready = _ready(polls)
    at_ready = polls[ready][1]
    grew = {k for _p, keys in polls[ready:] for s in SHELVES for k in keys[s] - at_ready[s]}
    assert dropped in at_ready["fresh"] | at_ready["popular"], "the verdict came before «ready»"
    assert dropped not in polls[-1][1]["fresh"] | polls[-1][1]["popular"]
    assert not grew, f"grew after ready: {sorted(grew)}"


def test_a_tile_dropped_after_ready_is_not_replaced_by_a_new_one(tmp_path: Path) -> None:
    """«Не играет» после «готово» полку только сужает: следующая картина места не занимает.

    Замер 02-10-2026: счётчик погас на 26.2 с, приговор снял плитку на 36.2 с, и на полку
    «Популярное» тут же встала новая картина - полка выросла после «готово».
    """
    cache = _cache(tmp_path, LIMIT + 1)
    cache.playable = lambda _query, key: key != "movie:картина-00:2026"
    ready: dict[str, set[str]] = {}
    publish = cache.publish

    def watched(shelf: str, tiles: list[JsonValue], *args: object, **kwargs: object) -> None:
        publish(shelf, tiles, *args, **kwargs)  # type: ignore[arg-type]
        keys = {str(tile.get("key")) for tile in tiles if isinstance(tile, dict)}
        if shelf in ready:
            assert keys <= ready[shelf], f"{shelf} grew after ready: {keys - ready[shelf]}"
        if not cache.filling:
            ready.setdefault(shelf, keys)

    cache.publish = watched  # type: ignore[method-assign]
    cache._rebuild()

    assert ready, "the counter went out during the pass"
    assert "Картина 00" not in " ".join(_titles(cache._body, "popular"))
    assert len(_titles(cache._body, "popular")) == LIMIT - 1


_CONDEMNED = "movie:картина-00:2026"


def _shows(cache: ShelvesCache) -> list[tuple[int, set[str], set[str]]]:
    """Каждая публикация: (номер захода, плитки захода, плитки тела после неё)."""
    shows: list[tuple[int, set[str], set[str]]] = []
    publish, feed, asked = cache.publish, cache.feed, [0]

    def counted(limit: int) -> FeedRows:
        asked[0] += 1
        return FeedRows(list(feed(limit)))

    def watched(shelf: str, tiles: list[JsonValue], *args: object, **kwargs: object) -> None:
        publish(shelf, tiles, *args, **kwargs)  # type: ignore[arg-type]
        body = cache._body or {}
        shown = body.get(shelf)
        after = (
            {str(t.get("key")) for t in shown if isinstance(t, dict)}
            if isinstance(shown, list)
            else set()
        )
        sent = {str(t.get("key")) for t in tiles if isinstance(t, dict)}
        shows.append((asked[0], sent, after))

    cache.feed, cache.publish = counted, watched  # type: ignore[method-assign]
    return shows


@pytest.mark.machine
def test_a_condemned_tile_does_not_come_back_from_the_old_body(tmp_path: Path) -> None:
    """«Не играет» снимает плитку и с экрана: тело прежнего правила её обратно не добивает.

    Прежде заход до «готово» публиковал без снятых, и добивка из старого тела ставила
    приговорённую плитку на её прежнее место, пока полку не закрывал приговор.
    """
    cache = _cache(tmp_path, 5)
    old: dict[str, JsonValue] = {
        shelf: [{"key": _CONDEMNED, "title": "Картина 00"}] for shelf in SHELVES
    }
    cache._body = {**old, "built_at": "2026-09-29T00:00:00+00:00", FIELD: RULE - 1}

    def playable(_query: str, key: str) -> bool:
        time.sleep(0.02)
        return key != _CONDEMNED

    cache.playable = playable
    shows = _shows(cache)
    cache._rebuild()

    gone = next(i for i, (_a, sent, _after) in enumerate(shows) if _CONDEMNED not in sent)
    back = [after for _a, _sent, after in shows[gone:] if _CONDEMNED in after]
    assert not back, f"the condemned tile came back {len(back)} times"


@pytest.mark.machine
def test_a_condemned_tile_does_not_come_back_on_the_next_pass(tmp_path: Path) -> None:
    """Приговор держится всю пересборку: следующий заход не показывает плитку до приговора.

    Первый заход осудил все плитки ленты, полки пусты, и пересборка спрашивает ленту снова.
    Прежде у второго захода приговоров ещё не было, и осуждённые вставали на полку.
    """
    cache = _cache(tmp_path, 5)
    sizes = iter([5, 10])
    cache.feed, cache.attempts = lambda _limit: _rows(next(sizes)), 2
    condemned = {f"movie:картина-{index:02d}:2026" for index in range(5)}

    def playable(_query: str, key: str) -> bool:
        time.sleep(0.02)
        return key not in condemned

    cache.playable = playable
    shows = _shows(cache)
    cache._rebuild()

    second = [(sent, after) for asked, sent, after in shows if asked == 2]
    assert second, "the rebuild did not ask the feed again"
    back = [sent | after for sent, after in second if (sent | after) & condemned]
    assert not back, f"condemned tiles came back on the next pass: {back}"
    assert _titles(cache._body, "fresh")
