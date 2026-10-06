"""Заход, которому TorrServer не ответил, не возвращает на полку честно снятые плитки."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.carried import CARRIED
from web.drop_count import DropCount
from web.dropped_marks import DROPPED, dropped_marks
from web.shelf_candidate import shelf_candidate

_MOMENT = datetime(2026, 10, 6, tzinfo=UTC)
_DROPPED = ["movie:15", "movie:16", "movie:17", "movie:18"]


def _tiles(keys: list[str]) -> list[JsonValue]:
    return [{"key": key} for key in keys]


def _numbered(count: int) -> list[str]:
    return [f"movie:{index}" for index in range(count)]


def _pruned() -> dict[str, JsonValue]:
    """Полка после живого захода: четыре плитки сняты как «не играет», 17 на экране."""
    return {
        FIELD: RULE,
        "fresh": _tiles(_numbered(5)),
        "popular": _tiles([key for key in _numbered(21) if key not in _DROPPED]),
        CARRIED: {"fresh": 0, "popular": 0},
        DROPPED: {"popular": list(_DROPPED)},
        "built_at": "earlier",
    }


def _blind(keys: list[str], played: frozenset[str] = frozenset()) -> DropCount:
    """Заход при лежащем TorrServer: приговор «играет» есть лишь у ``played``."""
    unknown = {key for key in keys if key not in played}
    return DropCount(checked=len(keys), unknown=len(unknown), unknown_keys=unknown)


def _rebuilt(drops: DropCount, keys: list[str]) -> dict[str, JsonValue]:
    shown = _pruned()
    body = shelf_candidate(
        shown, shown, "popular", _tiles(keys), drops, now=_MOMENT, limit=30, complete=True
    )
    assert body is not None
    return body


def test_a_pass_that_hears_only_unknown_does_not_put_dropped_tiles_back() -> None:
    """Живой контроль: TorrServer лёг, заход собрал 21 плитку «не знаю» - снятых нет."""
    body = _rebuilt(_blind(_numbered(21)), _numbered(21))

    assert body["popular"] == _pruned()["popular"]
    assert body[DROPPED] == {"popular": _DROPPED}


def test_a_tile_heard_playing_again_returns_and_its_mark_is_forgotten() -> None:
    """Раздача ожила: приговор «играет» возвращает плитку, вечного «негоден» нет."""
    body = _rebuilt(_blind(_numbered(21), played=frozenset({"movie:16"})), _numbered(21))

    assert {"key": "movie:16"} in body["popular"]  # type: ignore[operator]
    assert body[DROPPED] == {"popular": ["movie:15", "movie:17", "movie:18"]}


def test_an_unknown_tile_that_was_never_dropped_stays_on_the_shelf() -> None:
    """Защита от поломки цела: «не знаю» новую плитку не снимает."""
    body = _rebuilt(_blind([*_numbered(21), "movie:new"]), [*_numbered(21), "movie:new"])

    assert {"key": "movie:new"} in body["popular"]  # type: ignore[operator]


def test_a_mark_the_pass_did_not_ask_about_is_forgotten() -> None:
    """Память ограничена: ключ, о котором заход не спрашивал, из отметки уходит."""
    marks = dropped_marks(_pruned(), "popular", _blind(["movie:15"]))

    assert marks == {"popular": ["movie:15"]}


def test_a_new_drop_joins_the_mark_and_other_shelves_keep_theirs() -> None:
    """Новый честный отсев ложится в отметку своей полки, чужая полка не трогается."""
    body: dict[str, JsonValue] = {DROPPED: {"fresh": ["tv:1"], "popular": ["movie:15"]}}
    drops = DropCount(checked=2, dropped=1, unknown=1, dropped_keys={"movie:9"})
    drops.unknown_keys.add("movie:15")

    assert dropped_marks(body, "popular", drops) == {
        "fresh": ["tv:1"],
        "popular": ["movie:15", "movie:9"],
    }
