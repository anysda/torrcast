"""Проверяет сохранение плитки старого правила до нового честного отказа."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue
from web._stale_tiles import _keep_stale_tiles
from web.built_by_rule import FIELD, RULE
from web.drop_count import DropCount


def _current() -> dict[str, JsonValue]:
    """Предыдущая полка с одной плиткой, для которой меняется правило."""
    tile: JsonValue = {"key": "movie:kept:2026", "title": "Сохранённая"}
    return {FIELD: RULE - 1, "fresh": [tile], "popular": [], "built_at": None}


def test_an_unknown_stale_tile_stays_beside_the_new_tiles() -> None:
    """Нет нового приговора - прежняя плитка остаётся на экране."""
    new: JsonValue = {"key": "movie:new:2026", "title": "Новая"}

    kept, carried = _keep_stale_tiles(_current(), "fresh", [new], DropCount(), limit=30)

    assert [tile["key"] for tile in kept if isinstance(tile, dict)] == [
        "movie:new:2026",
        "movie:kept:2026",
    ]
    assert carried == 1


def test_a_new_false_verdict_removes_the_stale_tile() -> None:
    """Явный ``False`` нового отбора - единственная причина снять прежнюю плитку."""
    drops = DropCount(dropped=1, dropped_keys={"movie:kept:2026"})

    assert _keep_stale_tiles(_current(), "fresh", [], drops, limit=30) == ([], 0)


def test_a_stale_tile_never_takes_the_place_of_a_new_one() -> None:
    """Полка новым отбором полна - прежней плитке места нет, сколько бы её ни знали."""
    new: JsonValue = {"key": "movie:new:2026", "title": "Новая"}

    assert _keep_stale_tiles(_current(), "fresh", [new], DropCount(), limit=1) == ([new], 0)


def test_a_body_of_the_current_rule_carries_nothing() -> None:
    """Тело нынешнего правила не источник переноса: его плитки уже прошли новый отбор."""
    own = {**_current(), FIELD: RULE}

    assert _keep_stale_tiles(own, "fresh", [], DropCount(), limit=30) == ([], 0)
