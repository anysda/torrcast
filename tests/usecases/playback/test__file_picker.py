"""Зеркало выбора файла раздачи: серия сериала, крупнейший файл фильма или ``--file N``."""

from __future__ import annotations

import pytest

import torrcast.usecases.playback._show_state as _state
from torrcast.cli.args import Args
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback._file_picker import _default_file, _file_picker
from torrcast.usecases.select import _Plan


def _files() -> list[TorrFile]:
    return [
        TorrFile(index=1, name="кино/extra.mkv", size=1),
        TorrFile(index=2, name="кино/film.mkv", size=100),
        TorrFile(index=3, name="кино/readme.txt", size=1),
    ]


def _plan() -> _Plan:
    release = Release(raw_name="кино", title="Кино", magnet="magnet:?xt=1")
    return _Plan(
        picture=Picture(title="Кино", year=1999, releases=[release]),
        ranked=[release],
        runtime=7200.0,
        warn_mbit=16.0,
    )


def test_a_movie_takes_the_biggest_video_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """У фильма серии нет - берётся то, что назовёт медиатракт, а не первый попавшийся."""
    monkeypatch.setattr(_state, "pick_video_file", lambda files: max(files, key=lambda f: f.size))

    assert _default_file(_plan(), _plan().ranked[0], _files()).index == 2


def test_the_hand_named_number_counts_only_video_files() -> None:
    """``--file N`` считает ВИДЕО раздачи по порядку, а не файлы вперемешку с текстом."""
    chosen = _file_picker(Args(query=["кино"], file=2))

    assert chosen(_plan(), _plan().ranked[0], _files()).name.endswith("film.mkv")


def test_a_number_outside_the_pool_is_a_polite_refusal() -> None:
    """Номера нет - отказ называет, сколько видеофайлов в раздаче на самом деле."""
    chosen = _file_picker(Args(query=["кино"], file=9))

    with pytest.raises(NotFoundError, match="видеофайлов в раздаче 2"):
        chosen(_plan(), _plan().ranked[0], _files())


def test_without_the_flag_the_default_picker_is_returned() -> None:
    """Ручку не назвали - выбор остаётся обычным, и подмены на ней не бывает."""
    assert _file_picker(Args(query=["кино"])) is _default_file
