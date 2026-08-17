"""Выбор файла раздачи: самый крупный видеофайл, а образ диска - отказ навсегда."""

from __future__ import annotations

import pytest

from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torr_file import TorrFile

_GB = 1024**3


def test_the_film_is_the_biggest_video_of_the_torrent() -> None:
    """Рядом с фильмом лежат трейлеры и семплы, и они всегда мельче."""
    files = [
        TorrFile(0, "sample.mkv", 40 * 1024**2),
        TorrFile(1, "movie.mkv", 13 * _GB),
        TorrFile(2, "cover.jpg", 200 * 1024),
    ]

    assert pick_video_file(files).name == "movie.mkv"


def test_a_disc_image_is_refused_for_good_not_asked_again() -> None:
    """Метаданные приехали целиком, и ответ известен навсегда: видеофайла в раздаче нет.

    Отказ такого типа промолчавшая очередь второй раз не спрашивает - в отличие от
    :class:`InfraError`, который значит «про раздачу не узнали ничего».
    """
    files = [TorrFile(0, "VIDEO_TS/VTS_01_1.VOB", 4 * _GB), TorrFile(1, "info.nfo", 1024)]

    with pytest.raises(NotFoundError, match="похоже на образ диска"):
        pick_video_file(files)
    assert not issubclass(NotFoundError, InfraError), "второй спрос дал бы тот же ответ"


def test_the_extension_decides_and_case_does_not() -> None:
    """Имена в раздачах пишут как угодно, а расширение - единственная зацепка."""
    files = [TorrFile(0, "FILM.MKV", 2 * _GB), TorrFile(1, "readme.txt", 10 * _GB)]

    assert pick_video_file(files).name == "FILM.MKV"
