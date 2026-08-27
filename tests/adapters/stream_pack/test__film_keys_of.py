"""Зеркало :mod:`torrcast.adapters.stream_pack._film_keys_of`: индекс в карту показа.

Единица отделена ради одного: карту принятую и карту, отвергнутую как призрачную, собирает
ОДИН код. Разъедься они - у отвергнутой поехали бы либо дорожка, либо смещения, то есть
ровно то, ради чего её и оставляют на полке.
"""

from __future__ import annotations

from torrcast.adapters.stream_pack._film_keys_of import _film_keys_of
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point


def test_only_the_track_the_file_named_gets_into_the_map() -> None:
    """Дорожку называет сам файл: чужие точки в карту не идут, порядок пар сохранён."""
    points = (
        Point(0.0, 0, 1),
        Point(0.5, 512, 2),
        Point(2.0, 4096, 1),
        Point(2.5, 4600, 2),
    )
    found = _film_keys_of(KeyMap(60.0, points, 0, 0, "mkv", 1))

    assert (found.at, found.offset) == ([0.0, 2.0], [0, 4096])
    assert (found.duration, found.kind) == (60.0, "mkv")


def test_without_a_named_track_the_video_one_is_guessed_by_its_gaps() -> None:
    """``Tracks`` в голове не было - дорожку выбирает эвристика, а не первый номер подряд.

    Точек у звука больше, а пробелы в нём шире: карта обязана взять видео.
    """
    sound = tuple(Point(at, int(at * 10), 0) for at in (0.0, 1.0, 2.0, 32.0, 33.0, 60.0))
    video = tuple(Point(float(k * 2), k * 4096, 1) for k in range(31))
    found = _film_keys_of(KeyMap(60.0, tuple(sorted(sound + video)), 0, 0, "mkv", None))

    assert found.at == [float(k * 2) for k in range(31)], "взята дорожка звука вместо видео"
    assert found.offset == [k * 4096 for k in range(31)]


def test_the_seek_times_are_filtered_together_with_the_points() -> None:
    """Исковое время едет рядом с точками и режется тем же ситом: иначе оно разъедется.

    У mp4 без списка правок ``-ss`` ищет кадр по времени ДЕКОДИРОВАНИЯ, и порядок этого
    ряда совпадает с порядком точек - выбросить точку, не выбросив её время, значит
    подсунуть показу чужую секунду.
    """
    points = (Point(0.0, 0, 1), Point(1.0, 100, 2), Point(2.0, 4096, 1))
    found = _film_keys_of(KeyMap(60.0, points, 0, 0, "mp4", 1, via=(0.0, 0.9, 1.9)))

    assert found.via == (0.0, 1.9)


def test_a_map_without_seek_times_keeps_that_row_empty() -> None:
    """Искового времени нет - и выдумывать его нечем: пустой ряд означает «равно меткам»."""
    found = _film_keys_of(KeyMap(60.0, (Point(0.0, 0, 1), Point(2.0, 4096, 1)), 0, 0, "mkv", 1))

    assert found.via == ()
