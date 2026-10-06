"""Отказ сторожа публикации не держит на экране плитки, честно названные «не играет»."""

from __future__ import annotations

from datetime import UTC, datetime

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.carried import CARRIED
from web.drop_count import DropCount
from web.dropped_marks import DROPPED
from web.shelf_candidate import shelf_candidate
from web.shown_pruned import shown_pruned

_MOMENT = datetime(2026, 10, 6, tzinfo=UTC)


def _tiles(count: int) -> list[JsonValue]:
    return [{"key": f"movie:{index}"} for index in range(count)]


def _shown(popular: int, carried: int = 0) -> dict[str, JsonValue]:
    return {
        FIELD: RULE,
        "fresh": _tiles(5),
        "popular": _tiles(popular),
        CARRIED: {"fresh": 0, "popular": carried},
        "built_at": "earlier",
    }


def _judged(dropped: set[str], played: int, unknown: int) -> DropCount:
    """Счётчик живого захода: немного приговоров, остальное «не знаю»."""
    return DropCount(
        checked=len(dropped) + played + unknown,
        dropped=len(dropped),
        unknown=unknown,
        dropped_keys=set(dropped),
    )


def test_a_held_rebuild_still_takes_the_honest_drops_off_the_shown_shelf() -> None:
    """Живой случай: 5 из 7 приговоров «не играет», сторож держит тело, а их на полке нет."""
    shown = _shown(21)
    dropped = {"movie:15", "movie:16", "movie:17", "movie:18", "movie:40"}  # 40: not on screen
    drops = _judged(dropped, played=2, unknown=19)

    body = shelf_candidate(
        shown, shown, "popular", _tiles(26), drops, now=_MOMENT, limit=30, complete=True
    )

    assert body is not None
    assert body["popular"] == [*_tiles(15), *_tiles(21)[19:]]
    assert body["fresh"] == shown["fresh"]
    assert body["built_at"] == _MOMENT.isoformat()
    assert body[DROPPED] == {"popular": sorted(dropped)}  # a blind pass keeps them off


def test_unknown_verdicts_take_nothing_off_a_held_shelf() -> None:
    """TorrServer лёг: все приговоры «не знаю», сторож держит, и с полки ничего не снято."""
    shown = _shown(21)
    drops = _judged(set(), played=0, unknown=26)

    body = shelf_candidate(shown, shown, "popular", [], drops, now=_MOMENT, limit=30, complete=True)

    assert body is None


def test_a_broken_run_cannot_take_more_than_half_of_the_shelf() -> None:
    """Прогон, назвавший «не играет» больше половины полки, тело не трогает вовсе."""
    shown = _shown(20)
    drops = _judged({f"movie:{index}" for index in range(11)}, played=1, unknown=0)

    assert shown_pruned(shown, "popular", drops, _MOMENT) is None


def test_carried_tiles_keep_their_mark_when_one_of_them_is_dropped() -> None:
    """Перенесённая плитка тоже снимается, и отметка переноса не врёт про хвост."""
    shown = _shown(20, carried=4)
    drops = _judged({"movie:3", "movie:18"}, played=0, unknown=0)

    body = shown_pruned(shown, "popular", drops, _MOMENT)

    assert body is not None
    assert len(body["popular"]) == 18  # type: ignore[arg-type]
    assert body[CARRIED] == {"fresh": 0, "popular": 3}


def test_a_shelf_without_dropped_tiles_is_not_republished() -> None:
    """Снимать нечего - публиковать нечего: прежнее тело и так верно."""
    shown = _shown(20)
    drops = _judged({"movie:99"}, played=0, unknown=0)

    assert shown_pruned(shown, "popular", drops, _MOMENT) is None
