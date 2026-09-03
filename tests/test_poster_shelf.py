"""Зеркало :mod:`hass.poster_shelf`: постер на диске и имя файла отпечатком."""

from __future__ import annotations

from pathlib import Path

import pytest

from hass.poster_shelf import PosterShelf

POSTER = b"\xff\xd8\xff\xe0poster"


@pytest.fixture
def shelf(tmp_path: Path) -> PosterShelf:
    return PosterShelf(home=lambda: tmp_path / "posters")


def test_what_was_put_on_the_shelf_is_read_back(shelf: PosterShelf) -> None:
    shelf.write("Тачки|2006|movie", POSTER)
    assert shelf.read("Тачки|2006|movie") == POSTER


def test_a_picture_that_was_never_put_there_answers_with_nothing(shelf: PosterShelf) -> None:
    """Пустая полка равна полке, которой нет: спрашивать Википедию, а не падать."""
    assert shelf.read("Брат|1997|movie") is None


def test_a_name_from_a_torrent_never_becomes_a_path(tmp_path: Path, shelf: PosterShelf) -> None:
    """🔴 Название приезжает из раздачи и держит косую черту, точки и двоеточие.

    Собери имя файла из него - и запись уехала бы в чужой каталог. Имя файла тут
    отпечаток: всегда одно короткое имя внутри полки, чем бы ни назвали картину.
    """
    shelf.write("../../etc/passwd|0|movie", POSTER)
    written = list((tmp_path / "posters").iterdir())

    assert len(written) == 1
    assert written[0].parent == tmp_path / "posters"
    assert "/" not in written[0].name and ".." not in written[0].name
    assert shelf.read("../../etc/passwd|0|movie") == POSTER


def test_different_pictures_do_not_share_a_shelf_slot(shelf: PosterShelf) -> None:
    shelf.write("Тачки|2006|movie", POSTER)
    shelf.write("Тачки|2011|movie", b"\xff\xd8\xff\xe0another")

    assert shelf.read("Тачки|2006|movie") == POSTER
    assert shelf.read("Тачки|2011|movie") == b"\xff\xd8\xff\xe0another"


def test_a_shelf_that_cannot_be_written_stays_silent(tmp_path: Path) -> None:
    """Полка не путь показа: не записалось - показ этого даже не замечает."""
    wall = tmp_path / "wall"
    wall.write_text("не каталог", encoding="utf-8")
    closed = PosterShelf(home=lambda: wall / "posters")

    closed.write("Тачки|2006|movie", POSTER)

    assert closed.read("Тачки|2006|movie") is None
