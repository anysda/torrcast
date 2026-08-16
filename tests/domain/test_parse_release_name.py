"""Зеркало :mod:`torrcast.domain.parse_release_name`."""

from torrcast.domain.parse_release_name import _bare_episode_span, parse_release_name


def test_parse_release_name_is_exposed() -> None:
    assert parse_release_name is not None


def test_bare_episode_span_is_exposed() -> None:
    assert _bare_episode_span is not None
