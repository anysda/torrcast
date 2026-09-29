"""Checks that the console's search circle is what the search step takes."""

from __future__ import annotations

from hass.search import Search
from hass.searching import SEARCH
from torrcast.usecases.discover.search_circle import search_circle


def test_the_search_step_runs_the_consoles_circle_with_its_preview_seam() -> None:
    circle: Search = search_circle
    assert SEARCH is circle
