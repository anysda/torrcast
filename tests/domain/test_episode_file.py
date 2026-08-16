"""Tests for an episode recognized in a torrent file."""

from torrcast.domain.episode_file import EpisodeFile


def test_episode_file_exposes_series_position() -> None:
    item = EpisodeFile(3, 2, 5, "show.mkv", 100)
    assert str(item.at) == "s2e5"
