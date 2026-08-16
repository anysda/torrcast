"""Зеркало :mod:`torrcast.domain.episode_span`."""

from torrcast.domain.episode_span import _episode_span


def test_episode_span_is_exposed() -> None:
    assert _episode_span is not None
