"""Зеркало :mod:`torrcast.domain.both_languages`."""

from torrcast.domain.both_languages import _both_languages


def test_both_languages_is_exposed() -> None:
    assert _both_languages is not None
