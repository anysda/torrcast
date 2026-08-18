"""Договор сетки для ленты: слой сценариев знает о ней ровно эти восемь имён."""

from __future__ import annotations

from torrcast.adapters.stream_pack.grid import Grid
from torrcast.ports.feed_grid import FeedGrid

ASKED = ("count", "duration", "origin", "start", "end", "span", "slot_at", "manifest")


def test_the_port_names_exactly_what_the_feed_asks_of_a_grid() -> None:
    """Ни одного лишнего имени: протокол - это то, что сценарий имеет право спросить."""
    named = {name for name in vars(FeedGrid) if not name.startswith("_")}

    assert named == set(ASKED)


def test_the_real_grid_answers_every_name_of_the_port() -> None:
    """Боевая сетка адаптера отвечает на весь договор: иначе показ падал бы на живом."""
    grid = Grid.uniform(60.0, 10.0)

    for name in ASKED:
        assert hasattr(grid, name), f"сетка не отвечает на {name}"
    assert grid.count == 6 and grid.duration == 60.0
    assert grid.start(1) == 10.0 and grid.end(1) == 20.0 and grid.span(1) == 10.0
    assert grid.slot_at(25.0) == 2 and grid.manifest().startswith("#EXTM3U")
