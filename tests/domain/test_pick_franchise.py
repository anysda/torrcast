"""Зеркало :mod:`torrcast.domain.pick_franchise`."""

from torrcast.domain.pick_franchise import pick_franchise


def test_pick_franchise_is_exposed() -> None:
    assert pick_franchise is not None
