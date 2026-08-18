"""Зеркало :mod:`torrcast.domain.frames.mp4._moov`: где ``moov``, чья дорожка и её время.

Тут сидят два случая, каждый из которых уже стоил проекту карты: ``moov`` в хвосте за
двухгигабайтным ``mdat`` и список правок, сдвигающий всю дорожку.
"""

from __future__ import annotations

import pytest

from tests.domain.frames.mp4.boxes import Movie, Served
from torrcast.domain.frames.mp4._moov import (
    _edit_shift,
    _find_moov,
    _media_scale,
    _movie,
    _track_id,
    _video_trak,
)
from torrcast.domain.frames.mp4._window import _find, _Window
from torrcast.domain.infra_error import InfraError

HEAD = 512


def _opened(movie: Movie) -> tuple[Served, _Window, tuple[int, int]]:
    """Окно на ``moov`` пробного файла и границы его детей."""
    served = Served(movie.bytes())
    head = served.read(0, HEAD)
    at, size, header = _find_moov(served, head)
    return served, _Window(served, at, size, head[at:]), (header, size)


def test_moov_is_found_by_stepping_over_the_top_boxes_not_by_reading_them() -> None:
    """Шаг по верхним боксам - 16 байт заголовка, а не тело: ``mdat`` не читается."""
    served = Served(Movie(moov_last=True, mdat_size=1 << 20).bytes())
    head = served.read(0, 64)

    at, size, header = _find_moov(served, head)

    assert served.data[at + 4 : at + 8] == b"moov"
    assert header == 8 and size > 0
    assert served.taken < 1 << 20, "тело фильма в чтение не попало"


def test_a_file_without_moov_is_an_honest_error() -> None:
    """Гадать негде: без ``moov`` карты в mp4 нет вовсе."""
    served = Served(Movie().bytes().replace(b"moov", b"junk"))

    with pytest.raises(InfraError):
        _find_moov(served, served.read(0, HEAD))


def test_the_movie_header_gives_the_length_in_its_own_scale() -> None:
    """Длительность ``mvhd`` считана его же масштабом, а не масштабом дорожки."""
    _served, window, moov = _opened(Movie(movie_scale=90000, movie_length=450000))

    assert _movie(window, moov) == (90000, 5.0)


def test_the_video_track_is_the_one_that_calls_itself_vide() -> None:
    """``hdlr`` называет тип дорожки прямо - гадать по регулярности точек тут не нужно."""
    _served, window, moov = _opened(Movie(sound_first=True, track_id=4))
    trak = _video_trak(window, moov)

    assert _track_id(window, trak) == 4, "дорожка звука лежала первой и была пропущена"
    media = _find(window, *trak, b"mdia")
    assert media is not None
    assert _media_scale(window, media) == 600


def test_a_file_without_a_video_track_says_so() -> None:
    """Дорожки видео нет - карту брать не из чего, и молчать об этом нельзя."""
    _served, window, moov = _opened(Movie())
    broken = _Window(window.reader, window.base, window.size, window.data.replace(b"vide", b"soun"))

    with pytest.raises(InfraError):
        _video_trak(broken, moov)


def test_an_ordinary_edit_cuts_the_start_off_the_track() -> None:
    """``media_time >= 0`` выкидывает начало дорожки - так YTS срезает два кадра.

    Сдвиг считан масштабом ДОРОЖКИ: перепутай его с масштабом фильма - и вся карта уедет.
    """
    _served, window, moov = _opened(Movie(edit=(6000, 150)))
    trak = _video_trak(window, moov)

    assert _edit_shift(window, trak, 1000, 600) == 0.25


def test_an_empty_edit_delays_the_track_and_is_counted_in_the_movie_scale() -> None:
    """Пустая правка (``media_time = -1``) вставляет паузу, и задана она масштабом ФИЛЬМА.

    Принять её за «ничего не делает» - потерять 6 мс на всей карте: ровно так ремукс mkv в
    mp4 и промахивался мимо опорных кадров.
    """
    _served, window, moov = _opened(Movie(edit=(500, -1)))
    trak = _video_trak(window, moov)

    assert _edit_shift(window, trak, 1000, 600) == -0.5


def test_no_edit_list_means_no_shift_at_all() -> None:
    """Правок нет - и сдвига нет: выдумывать его неоткуда."""
    _served, window, moov = _opened(Movie())
    trak = _video_trak(window, moov)

    assert _edit_shift(window, trak, 1000, 600) == 0.0
