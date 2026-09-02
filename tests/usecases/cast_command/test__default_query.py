"""Зеркало запроса показа, когда зритель не назвал картину."""

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._default_query import _default_query


def _serial(title: str, query: str, updated: str) -> Entry:
    return Entry(
        title=title,
        magnet="m",
        query=query,
        kind="tv",
        season=1,
        episode=1,
        episodes=[[1, 1, 0], [1, 2, 1]],
        updated=updated,
    )


def test_the_latest_serial_supplies_its_saved_query() -> None:
    state = WatchState()
    state.entries["tv:старый:2025"] = _serial("Старый", "старый", "2026-09-01")
    state.entries["tv:новый:2026"] = _serial("Новый", "исходный-запрос", "2026-09-02")

    assert _default_query(state) == "исходный-запрос"


def test_an_empty_serial_history_supplies_cars_2006() -> None:
    state = WatchState(
        {"movie:новый:2026": Entry(title="Новый фильм", magnet="m", updated="2026-09-02")}
    )

    assert _default_query(state) == "Cars 2006"
