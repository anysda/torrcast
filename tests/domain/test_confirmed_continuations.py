"""Зеркало :mod:`torrcast.domain.confirmed_continuations`."""

from torrcast.domain.confirmed_continuations import confirmed_continuations


def test_confirmed_continuations_is_exposed() -> None:
    assert confirmed_continuations is not None
