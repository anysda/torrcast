"""Зеркало :mod:`torrcast.domain.fansub_episode`."""

from torrcast.domain.fansub_episode import _fansub_episode


def test_fansub_episode_is_exposed() -> None:
    assert _fansub_episode is not None
