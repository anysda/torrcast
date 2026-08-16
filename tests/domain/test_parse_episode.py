"""Tests for parsing season and episode numbers."""

from torrcast.domain.parse_episode import parse_episode


def test_scene_and_russian_episode_notation_are_parsed() -> None:
    scene = parse_episode("Show.S02E05.mkv")
    russian = parse_episode("2 сезон 5 серия")
    assert scene and (scene.season, scene.episode) == (2, 5)
    assert russian and (russian.season, russian.episode) == (2, 5)
