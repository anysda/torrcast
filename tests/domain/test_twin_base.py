"""Checks that a twin's name leads back to its tracker and other names stay as they are."""

from __future__ import annotations

from torrcast.domain.twin_base import TWIN, twin_base


def test_a_twins_rows_are_its_trackers() -> None:
    assert twin_base("RuTor" + TWIN) == "RuTor"


def test_any_other_name_stays_as_it_is() -> None:
    assert twin_base("Knaben") == "Knaben"
