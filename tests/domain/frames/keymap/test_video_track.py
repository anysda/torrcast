"""Зеркало :mod:`torrcast.domain.frames.keymap.video_track`: какая дорожка карты - видео.

Вопрос этот стоит ради mkv: ``Cues`` пишутся и для звука с субтитрами, а сетку сегментов
режут по видео. Ошибись выбор - границы встали бы по звуковым точкам, и каждый кусок
начинался бы не с опорного кадра.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.frames.keymap.video_track import video_track


def test_the_regular_track_wins_over_the_crowded_one() -> None:
    """Побеждает самый короткий наибольший пробел, а не число точек.

    У «Моаны 2» самая многочисленная дорожка (1786 точек) - это звук с пробелами до 65 с,
    а у видео их 1119 и не больше 10.4 с. Считай мы точки - сетка легла бы по звуку.
    """
    dense = [Point(at, int(at * 10), 2) for at in (0.0, 0.1, 0.2, 0.3, 40.0)]
    steady = [Point(at, int(at * 10), 1) for at in (0.0, 10.0, 20.0, 30.0)]

    assert video_track(tuple(dense + steady)) == 1


def test_a_single_track_is_the_answer_without_any_guessing() -> None:
    """У mp4 разбор отдаёт точки одной дорожки - тогда выбирать не из чего."""
    only = tuple(Point(at, 0, 7) for at in (0.0, 1.0, 2.0))

    assert video_track(only) == 7
