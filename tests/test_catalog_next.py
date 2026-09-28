"""Плашка «Следующая серия» за краем раздачи: каталог сериала и сезоны пула раздач."""

from __future__ import annotations

from collections.abc import Callable

from hass.catalog_next import catalog_next
from torrcast.domain.entry import Entry
from torrcast.runtime.series_facts import SeriesFacts

KEY = "tv:рик-и-морти:2013"


def test_the_plate_does_not_promise_an_announced_season() -> None:
    entry = Entry(
        title="Рик и Морти", magnet="m", kind="tv", season=9, episode=10,
        episodes=[[9, 10, 0, 0]], query="rick-and-morty",
    )  # fmt: skip
    catalog = SeriesFacts(
        lambda *_a: "tt2861424",
        lambda _t: {9: tuple(range(1, 11)), 10: (1,)},
        lambda *_a: ({}, False),
    )
    asked: list[tuple[str, str]] = []

    def pool(*seasons: int) -> Callable[[str, str], tuple[int, ...]]:
        def seen(key: str, query: str) -> tuple[int, ...]:
            asked.append((key, query))
            return seasons

        return seen

    assert catalog_next(entry, KEY, "rick and morty", catalog, pool(8, 9)) is None
    assert catalog_next(entry, KEY, "rick and morty", catalog, pool(9, 10)) == "s10e1"
    assert asked == [(KEY, "rick and morty")] * 2
