"""Зеркало :mod:`torrcast.domain.frames.keymap.point`: опорный кадр как значение.

Точка - общий язык двух разборов: mkv и mp4 обязаны отдавать ОДНО и то же, иначе «сетка по
опорным кадрам» значила бы разное в зависимости от контейнера.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.point import Point


def test_a_point_says_when_where_and_whose_in_that_order() -> None:
    """Порядок полей - договор: точки сортируются кортежем, то есть по времени."""
    assert tuple(Point(1.5, 2048, 3)) == (1.5, 2048, 3)
    assert (Point(1.5, 0, 0).at, Point(0.0, 7, 0).offset, Point(0.0, 0, 4).track) == (1.5, 7, 4)


def test_points_sort_by_time_and_not_by_the_byte_they_lie_at() -> None:
    """Карта едет наружу отсортированной, и сортируется она временем показа.

    Отсортируйся она байтом - перемотка на нужную секунду искала бы кадр не там: в файле
    порядок кусков и порядок времён совпадают не всегда.
    """
    late = Point(9.0, 10, 1)
    early = Point(1.0, 900, 1)

    assert sorted([late, early]) == [early, late]
