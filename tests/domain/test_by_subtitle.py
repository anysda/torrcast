"""Зеркало :mod:`torrcast.domain.by_subtitle`."""

from torrcast.domain.by_subtitle import _by_subtitle


def test_by_subtitle_is_exposed() -> None:
    assert _by_subtitle is not None
