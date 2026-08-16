"""Зеркало :mod:`torrcast.domain.with_subtitled`."""

from torrcast.domain.with_subtitled import _with_subtitled


def test_with_subtitled_is_exposed() -> None:
    assert _with_subtitled is not None
