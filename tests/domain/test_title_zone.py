"""Зеркало :mod:`torrcast.domain.title_zone`."""

from torrcast.domain.title_zone import _title_zone


def test_title_zone_is_exposed() -> None:
    assert _title_zone is not None
