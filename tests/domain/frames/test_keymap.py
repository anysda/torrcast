"""Проверяет модели и выбор видеодорожки карты."""

from torrcast.domain.frames.keymap import Point, video_track


def test_video_track_has_smallest_largest_gap() -> None:
    """Регулярная дорожка побеждает редкую."""
    points = (Point(0, 0, 1), Point(2, 1, 1), Point(0, 2, 2), Point(20, 3, 2))
    assert video_track(points) == 1
