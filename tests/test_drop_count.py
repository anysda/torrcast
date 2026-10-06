"""Счётчик прогона отбора: считает каждый вызов, «не знаю» не давит долю отброшенных."""

from __future__ import annotations

from web.drop_count import DropCount
from web.shelf_tiles import Playable


def _playable(verdicts: dict[str, bool | None]) -> Playable:
    def _of(query: str, key: str) -> bool | None:
        return verdicts[key]

    return _of


def test_the_ratio_excludes_unknown_from_both_sides() -> None:
    """Половина честных «не играет», а «не знаю» - ни в числителе, ни в знаменателе."""
    counted = DropCount()
    playable = counted.wrap(_playable({"a": True, "b": False, "c": None, "d": None}))

    assert [playable("q", key) for key in ("a", "b", "c", "d")] == [True, False, None, None]
    assert counted.checked == 4
    assert counted.dropped == 1
    assert counted.unknown == 2
    assert counted.ratio == 0.5


def test_the_ratio_is_zero_with_nothing_confirmed_yet() -> None:
    """Заход ещё не проверил ни одной картины - долю нечем делить, счётчик не роняет."""
    assert DropCount().ratio == 0.0


def test_wrap_does_not_change_the_honest_verdict() -> None:
    """Обёртка считает, но приговор наружу идёт ровно тот, что вернул исходный порт."""
    counted = DropCount()
    playable = counted.wrap(_playable({"a": True}))

    assert playable("q", "a") is True


def test_the_counter_names_which_tiles_were_unknown() -> None:
    """Ключи «не знаю» нужны отметке снятых (:mod:`web.dropped_marks`): незнание не возвращает."""
    counted = DropCount()
    playable = counted.wrap(_playable({"a": True, "b": False, "c": None}))

    for key in ("a", "b", "c"):
        playable("q", key)

    assert counted.unknown_keys == {"c"}
    assert counted.dropped_keys == {"b"}
