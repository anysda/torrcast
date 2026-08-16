"""Tests for removing episode notation from a query."""

from torrcast.domain.split_episode import split_episode


def test_episode_suffix_is_removed_whole() -> None:
    title, episode = split_episode("киберпанк 2 сезон 5 серия")
    assert title == "киберпанк"
    assert episode and (episode.season, episode.episode) == (2, 5)
