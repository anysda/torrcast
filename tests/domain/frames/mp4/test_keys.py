"""Зеркало :mod:`torrcast.domain.frames.mp4.keys`: пять таблиц ``moov`` в одну карту.

Мера тут одна и она про карту: время опорного кадра и абсолютный байт, с которого его
данные начинаются. Ошибись сборка на одну таблицу - граница сегмента перестанет попадать
на опорный кадр, и перемотка вместо картинки даст чёрный экран.
"""

from __future__ import annotations

import pytest

from tests.domain.frames.mp4.boxes import Movie, Served
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.mp4.keys import keys
from torrcast.domain.infra_error import InfraError

HEAD = 512


def _map(movie: Movie) -> tuple[Served, KeyMap]:
    served = Served(movie.bytes())
    return served, keys(served, served.read(0, HEAD))


def test_the_five_tables_add_up_to_times_and_absolute_bytes() -> None:
    """Опорные сэмплы, их время и смещение чанка сходятся в одну карту."""
    served, found = _map(Movie())

    assert found.kind == "mp4"
    assert found.duration == 6.0, "длительность берётся из mvhd в его собственном масштабе"
    assert [(p.at, p.offset, p.track) for p in found.points] == [(0.0, 1000, 1), (0.5, 3000, 1)]
    assert found.requests == served.requests


def test_a_missing_stss_means_every_frame_is_a_key_frame() -> None:
    """Нет ``stss`` - опорный каждый сэмпл: так подписаны файлы без B-кадров."""
    _served, found = _map(Movie(sync=[]))

    assert [p.at for p in found.points] == [0.0, 0.25, 0.5, 0.75]


def test_the_edit_list_shifts_the_whole_map_and_is_never_skipped() -> None:
    """``elst`` с ненулевым ``media_time`` сдвигает ВСЮ карту - на этом горели разборы.

    У YTS-релизов ``media_time`` равен двум кадрам, и без него граница сегмента промахи-
    вается мимо опорного кадра на десятки миллисекунд.
    """
    _served, shifted = _map(Movie(edit=(6000, 150)))

    assert [p.at for p in shifted.points] == [-0.25, 0.25], "сдвиг снят со всех точек разом"


def test_an_empty_edit_inserts_a_pause_instead_of_cutting_the_start() -> None:
    """Пустая правка (``media_time = -1``) наоборот вставляет паузу - и в масштабе ФИЛЬМА.

    Принять её за «ничего не делает» - потерять 6 мс на всей карте: ровно так ремукс mkv
    в mp4 и уезжал мимо опорных кадров.
    """
    _served, delayed = _map(Movie(edit=(500, -1)))

    assert [p.at for p in delayed.points] == [0.5, 1.0], "пауза считана масштабом фильма"


def test_the_composition_offset_turns_decode_time_into_shown_time() -> None:
    """``ctts`` - это разница между «когда декодировать» и «когда показать»."""
    _served, found = _map(Movie(composition=[(4, 300)]))

    assert [p.at for p in found.points] == [0.5, 1.0]


def test_a_movie_without_moov_says_so_instead_of_reading_the_film() -> None:
    """Нет ``moov`` - честная ошибка: тянуть гигабайты в поисках его незачем."""
    served = Served(Movie().bytes().replace(b"moov", b"junk"))

    with pytest.raises(InfraError):
        keys(served, served.read(0, HEAD))


def test_the_map_is_taken_without_reading_the_film_itself() -> None:
    """``mdat`` в два гигабайта не читается ни байтом, даже когда ``moov`` за ним.

    Цена карты у холодной раздачи - это байты и заходы, а не точки: прочитай разбор
    ``mdat``, старт показа встал бы на минуты.
    """
    served, found = _map(Movie(moov_last=True, mdat_size=1 << 20))

    assert found.points, "moov в хвосте всё равно находится"
    assert served.taken < 1 << 20, "тело фильма в чтение не попало"
