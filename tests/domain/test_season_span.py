"""Зеркало :mod:`torrcast.domain.season_span`."""

from torrcast.domain.season_span import _season_span


def test_season_span_is_exposed() -> None:
    assert _season_span is not None
