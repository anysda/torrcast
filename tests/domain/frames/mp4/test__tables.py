"""Зеркало :mod:`torrcast.domain.frames.mp4._tables`: пять сжатых таблиц ``stbl``.

Каждая из них отвечает на свой вопрос - какой сэмпл опорный, когда он и где лежит, - и
все три разбора идут СЛИЯНИЕМ двух отсортированных списков. Поиском по таблице на каждый
кадр разбор уже был, и стоил он 18.5 с чистого процессора.
"""

from __future__ import annotations

import pytest

from tests.domain.frames.mp4.boxes import Movie, Served
from torrcast.domain.frames.mp4._moov import _find_moov, _video_trak
from torrcast.domain.frames.mp4._tables import (
    _composition,
    _offsets,
    _sample_sizes,
    _sample_times,
    _sync_samples,
)
from torrcast.domain.frames.mp4._window import _find, _Window
from torrcast.domain.infra_error import InfraError

HEAD = 512


def _stbl(movie: Movie) -> tuple[_Window, tuple[int, int]]:
    """Окно на ``moov`` и границы таблиц дорожки видео."""
    served = Served(movie.bytes())
    head = served.read(0, HEAD)
    at, size, header = _find_moov(served, head)
    window = _Window(served, at, size, head[at:])
    trak = _video_trak(window, (header, size))
    media = _find(window, *trak, b"mdia")
    assert media is not None
    minf = _find(window, *media, b"minf")
    assert minf is not None
    tables = _find(window, *minf, b"stbl")
    assert tables is not None
    return window, tables


def test_the_key_frames_are_the_ones_stss_names() -> None:
    """Есть ``stss`` - опорные ровно перечисленные в ней, считая с единицы."""
    window, stbl = _stbl(Movie(sync=[1, 3, 7]))

    assert _sync_samples(window, stbl, 8) == [1, 3, 7]


def test_without_stss_every_sample_is_a_key_frame() -> None:
    """Таблицы нет - опорный каждый: так подписаны файлы без B-кадров."""
    window, stbl = _stbl(Movie(sync=[]))

    assert _sync_samples(window, stbl, 4) == [1, 2, 3, 4]


def test_the_times_are_merged_through_the_compressed_runs() -> None:
    """``stts`` сжата пачками «столько-то подряд по столько-то» - её разворачивают слиянием."""
    window, stbl = _stbl(Movie(times=[(2, 100), (3, 50)]))

    assert _sample_times(window, stbl, [1, 2, 3, 5]) == [0, 100, 200, 300]


def test_a_movie_without_stts_says_so_instead_of_guessing_the_times() -> None:
    """Времён кадров взять неоткуда - это ошибка, а не пустая карта."""
    served = Served(Movie().bytes().replace(b"stts", b"junk"))
    head = served.read(0, HEAD)
    at, size, header = _find_moov(served, head)
    window = _Window(served, at, size, head[at:])
    trak = _video_trak(window, (header, size))
    media = _find(window, *trak, b"mdia")
    assert media is not None
    minf = _find(window, *media, b"minf")
    assert minf is not None
    stbl = _find(window, *minf, b"stbl")
    assert stbl is not None

    with pytest.raises(InfraError):
        _sample_times(window, stbl, [1])


def test_a_sample_inside_a_chunk_is_offset_by_its_predecessors() -> None:
    """Сэмплов в чанке несколько - смещение считается ``stsz``-размерами тех, кто перед ним.

    У YTS сэмпл в чанке один, и промах тут не виден вовсе; на паках он даёт байт мимо кадра.
    """
    window, stbl = _stbl(Movie(chunks=[(1, 2, 1)], offsets=[1000, 2000], sample_size=10))

    assert _offsets(window, stbl, [1, 2, 3, 4]) == [1000, 1010, 2000, 2010]


def test_the_sample_sizes_come_from_the_common_size_when_there_is_one() -> None:
    """``stsz`` с общим размером - это тот же размер на все сэмплы, а не пустая таблица."""
    window, stbl = _stbl(Movie(sample_size=7, sample_count=3))

    assert _sample_sizes(window, stbl) == [7, 7, 7]


def test_the_composition_offsets_are_read_only_for_the_asked_samples() -> None:
    """``ctts`` - разница «декодировать» и «показать»; спрашивают её про опорные кадры."""
    window, stbl = _stbl(Movie(composition=[(2, 300), (2, 0)]))

    assert _composition(window, stbl, [1, 3]) == {1: 300, 3: 0}


def test_no_ctts_means_no_offsets_at_all() -> None:
    """Нет таблицы - нет и B-кадров, а значит и сдвига: выдумывать его нельзя."""
    window, stbl = _stbl(Movie())

    assert _composition(window, stbl, [1, 3]) == {}
