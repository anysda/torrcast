"""Checks that a twin is off whenever its tracker is off."""

from __future__ import annotations

from torrcast.domain.twin_follows import twin_follows

_KNABEN = (1, "Knaben")
_RUTOR = (2, "RuTor")
_TWIN = (6, "RuTor names")


def test_a_twin_of_a_disabled_tracker_is_dropped() -> None:
    assert twin_follows([_KNABEN, _TWIN]) == [_KNABEN]


def test_a_twin_of_an_enabled_tracker_stays() -> None:
    assert twin_follows([_KNABEN, _RUTOR, _TWIN]) == [_KNABEN, _RUTOR, _TWIN]
