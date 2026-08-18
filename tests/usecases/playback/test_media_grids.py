"""Зеркало завода сетки: настоящий ``grid_for`` строит её теми доводами, что объявлены."""

from __future__ import annotations

from torrcast.adapters.stream_pack.grid_for import grid_for
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.playback.media_grids import MediaGrids


def test_a_source_without_a_keymap_falls_back_to_an_even_grid_out_loud() -> None:
    """Карту снять не с чего - сетка ровная, и подмена нарезки не молчаливая."""
    named: MediaGrids = grid_for
    said: list[str] = []

    made: MediaGrid = named("file:///нет-такого", 300.0, 10.0, True, say=said.append)

    assert made.count > 0
    assert made.duration == 300.0
    assert made.on_keys is False
    assert said, "подмена нарезки обязана быть сказана вслух"
