"""Проверки маркера отсутствующего показа."""

from torrcast.domain.not_raised import NOT_RAISED


def test_marker_cannot_be_movie_position() -> None:
    assert NOT_RAISED < 0
