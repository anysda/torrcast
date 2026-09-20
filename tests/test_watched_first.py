"""Зеркало TC-1329: смотренная через torrcast картина встаёт первой в готовой выдаче."""

from __future__ import annotations

from typing import Any, cast

import pytest

from hass import watched_first as wf
from hass.watched_first import watched_first
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store import slot as state_slot


def _hit(key: str, pick: int, *, default: bool = False) -> JsonValue:
    return {"pick": pick, "key": key, "default": default}


def _records(hits: list[JsonValue]) -> list[dict[str, Any]]:
    """Записи выдачи под своим видом: договор обещает объекты, а не любой JSON."""
    assert all(isinstance(hit, dict) for hit in hits), "запись выдачи - объект"
    return cast("list[dict[str, Any]]", hits)


def _remember(entries: dict[str, Entry]) -> None:
    fake = FakeStateStore()
    state = fake.load()
    state.entries.update(entries)
    fake.save(state)
    state_slot.install(fake)


def _entry(title: str, *, done: bool = False) -> Entry:
    # 1443.9 с при 100-секундной "длине" - как в жизни: запись недосмотрена, но она есть.
    pos = 100.0 if done else 14.39
    return Entry(title, f"magnet:{title}", kind="tv", pos=pos, dur=100.0, updated="2026-01-01")


def test_a_watched_picture_moves_to_the_front() -> None:
    """Ровно случай карточки: находка стоит последней, но её уже смотрели."""
    ghost = "tv:призрак-в-доспехах:2026"
    _remember({ghost: _entry("Призрак")})
    hits = [_hit("movie:a:2020", 1), _hit("movie:b:2021", 2), _hit(ghost, 3)]

    result = _records(watched_first(hits))

    assert [r["key"] for r in result] == [ghost, "movie:a:2020", "movie:b:2021"]
    assert [r["pick"] for r in result] == [3, 1, 2], "номер pick остаётся адресом, а не местом"


def test_no_history_at_all_leaves_the_list_untouched() -> None:
    """Три запроса без истории - три раза одна и та же проверка: список не поменялся."""
    _remember({})
    for hits in (
        [_hit("movie:a:2020", 1), _hit("movie:b:2021", 2)],
        [_hit("tv:c:2022", 1)],
        [],
    ):
        assert watched_first(hits) == hits


def test_a_query_with_history_of_a_different_picture_is_untouched() -> None:
    """История есть, но ни одна находка круга ей не отвечает - перестановки нет."""
    _remember({"movie:другая-картина:2019": _entry("Другая")})
    hits = [_hit("movie:a:2020", 1), _hit("movie:b:2021", 2)]

    assert watched_first(hits) == hits


def test_several_watched_pictures_keep_their_relative_order() -> None:
    """Несколько смотренных в одной выдаче - все первые, порядок между ними как был."""
    _remember({"movie:b:2021": _entry("B"), "movie:d:2023": _entry("D")})
    hits = [
        _hit("movie:a:2020", 1),
        _hit("movie:b:2021", 2),
        _hit("movie:c:2022", 3),
        _hit("movie:d:2023", 4),
    ]

    result = _records(watched_first(hits))

    keys = [r["key"] for r in result]
    assert keys == ["movie:b:2021", "movie:d:2023", "movie:a:2020", "movie:c:2022"]


def test_an_entry_watched_to_the_end_still_counts_as_already_watched() -> None:
    """Граница способа: «смотрели» не значит «досматривают» - запись есть, и этого хватает.

    :attr:`torrcast.domain.entry.Entry.watched` (95%+ пройдено) отвечает на другой вопрос
    и тут не спрашивается: карточка просит признак «уже смотрели через torrcast», а не
    «есть незаконченная закладка».
    """
    entry = _entry("Done", done=True)
    assert entry.watched, "довод теста: запись действительно досмотрена"
    _remember({"movie:done:2020": entry})
    hits = [_hit("movie:a:2020", 1), _hit("movie:done:2020", 2)]

    result = _records(watched_first(hits))

    assert [r["key"] for r in result] == ["movie:done:2020", "movie:a:2020"]


def test_the_default_flag_stays_on_its_own_record_after_the_move() -> None:
    """Метка ``default`` едет полем записи, а не местом - перестановка её не путает."""
    _remember({"movie:b:2021": _entry("B")})
    hits = [_hit("movie:a:2020", 1, default=True), _hit("movie:b:2021", 2)]

    result = _records(watched_first(hits))

    flagged = [r["key"] for r in result if r["default"]]
    assert flagged == ["movie:a:2020"], "взятая картина осталась той же, пусть и не первой строкой"


def test_no_assembled_state_store_leaves_the_order_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Слот вовсе не собран (:mod:`tests.hass_integration`, форма ответа в обход `wire()`).

    Это не отказ выдачи целиком - признака просто неоткуда взять, и список остаётся тем,
    что был.
    """

    def _unassembled() -> Any:
        raise RuntimeError("no state store assigned: the app is not assembled")

    monkeypatch.setattr(wf, "store", _unassembled)
    hits = [_hit("movie:a:2020", 1), _hit("movie:b:2021", 2)]

    assert watched_first(hits) == hits
