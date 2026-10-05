"""Checks that the picture's names go to a tracker's twin and the viewer's text to the tracker."""

from __future__ import annotations

from torrcast.domain.names_twin import by_circle, twin_base

_PAIRS = [(1, "Knaben"), (2, "RuTor"), (4, "JacRed"), (6, "RuTor names")]


def test_the_viewers_text_never_asks_the_twin() -> None:
    assert by_circle(_PAIRS, names=False) == [(1, "Knaben"), (2, "RuTor"), (4, "JacRed")]


def test_the_names_ask_the_twin_instead_of_its_tracker() -> None:
    assert by_circle(_PAIRS, names=True) == [(1, "Knaben"), (4, "JacRed"), (6, "RuTor names")]


def test_without_its_twin_the_tracker_keeps_the_names() -> None:
    pairs = _PAIRS[:3]
    assert by_circle(pairs, names=True) == pairs
    assert by_circle(pairs, names=False) == pairs


def test_a_twins_rows_are_its_trackers() -> None:
    assert twin_base("RuTor names") == "RuTor"
    assert twin_base("Knaben") == "Knaben"
