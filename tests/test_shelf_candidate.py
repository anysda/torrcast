"""Проверяет кандидата на публикацию: перенос, отметка, клеймо и порог усыхания."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.carried import CARRIED
from web.drop_count import DropCount
from web.shelf_candidate import shelf_candidate

_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)


def _tiles(prefix: str, count: int) -> list[JsonValue]:
    return [{"key": f"{prefix}{index}"} for index in range(count)]


def _body(rule: int, fresh: int, popular: int) -> dict[str, JsonValue]:
    return {
        FIELD: rule,
        "fresh": _tiles("old", fresh),
        "popular": _tiles("old", popular),
        "built_at": None,
    }


def test_the_first_shelf_of_a_new_rule_is_topped_up_and_marked_without_the_new_stamp() -> None:
    """Первая полка пересборки добита старыми плитками, клеймо ждёт последнюю полку."""
    alien = _body(RULE - 1, 25, 25)

    body = shelf_candidate(
        alien, alien, "fresh", _tiles("new", 18), DropCount(), now=_MOMENT, limit=30, complete=False
    )

    assert body is not None
    assert body[FIELD] == RULE - 1
    assert body["fresh"] == [*_tiles("new", 18), *_tiles("old", 12)]
    assert body[CARRIED] == {"fresh": 12, "popular": 0}
    assert body["built_at"] == _MOMENT.isoformat()


def test_the_last_shelf_stamps_the_new_rule_and_keeps_the_neighbours_mark() -> None:
    """Клеймо ставит последняя полка, отметка соседней полки остаётся её."""
    alien = _body(RULE - 1, 25, 25)
    current: dict[str, JsonValue] = {**alien, CARRIED: {"fresh": 12, "popular": 0}}

    body = shelf_candidate(
        current,
        alien,
        "popular",
        _tiles("new", 30),
        DropCount(),
        now=_MOMENT,
        limit=30,
        complete=True,
    )

    assert body is not None
    assert body[FIELD] == RULE
    assert body[CARRIED] == {"fresh": 12, "popular": 0}
    assert body["popular"] == _tiles("new", 30)


def test_a_drastically_shrunk_shelf_of_the_same_rule_is_not_a_candidate() -> None:
    """Полка своего правила, усохшая больше чем вдвое, прежнюю не заменяет."""
    own = _body(RULE, 20, 20)

    body = shelf_candidate(
        own, own, "fresh", _tiles("new", 5), DropCount(), now=_MOMENT, limit=30, complete=True
    )

    assert body is None
