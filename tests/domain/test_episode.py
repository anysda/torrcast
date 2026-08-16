"""Зеркало :mod:`torrcast.domain.episode`."""

from torrcast.domain.episode import Episode


def test_episode_is_exposed() -> None:
    assert Episode is not None
