"""Зеркало выбора файла картины в раздаче-сборнике."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback.collection_part import collection_part
from torrcast.usecases.playback.file_picker import _default_file
from torrcast.usecases.playback.pack_note import pack_note
from torrcast.usecases.select.plan import Plan

_GIB = 2**30
_DUNE = "Дюна: Дилогия / Dune: Dilogy / 2021-2024 / ДБ / HEVC, HDR / BDRip (1080p)"
_MATRIX = "Матрица: Трилогия / The Matrix: Trilogy (1999-2003) BDRip 1080p"


def _release(raw_name: str, collection: bool = True) -> Release:
    return Release(raw_name=raw_name, title="Сборник", magnet="magnet:?xt=1", collection=collection)


def _dune() -> list[TorrFile]:
    """Живая раздача: вторая часть крупнее первой."""
    return [
        TorrFile(index=1, name="Дюна/Дюна 1.hdr.mkv", size=int(4.43 * _GIB)),
        TorrFile(index=2, name="Дюна/Дюна 2.hdr.mkv", size=int(4.54 * _GIB)),
    ]


def _matrix() -> list[TorrFile]:
    return [
        TorrFile(index=1, name="Matrix/The.Matrix.1999.1080p.mkv", size=9 * _GIB),
        TorrFile(index=2, name="Matrix/The.Matrix.Reloaded.2003.1080p.mkv", size=11 * _GIB),
        TorrFile(index=3, name="Matrix/The.Matrix.Revolutions.2003.1080p.mkv", size=10 * _GIB),
    ]


def _plan(title: str, year: int, release: Release) -> Plan:
    return Plan(
        picture=Picture(title=title, year=year, releases=[release]),
        ranked=[release],
        runtime=9000.0,
        warn_mbit=16.0,
    )


def test_the_first_film_of_a_dilogy_plays_its_own_file_not_the_largest() -> None:
    """«Дюна» (2021) из дилогии 2021-2024 играла «Дюна 2.hdr.mkv» - крупнейший файл."""
    release = _release(_DUNE)

    chosen = _default_file(_plan("Дюна", 2021, release), release, _dune())

    assert chosen.name == "Дюна/Дюна 1.hdr.mkv"


def test_the_one_file_with_the_picture_s_year_is_its_file() -> None:
    assert (
        collection_part(Picture(title="Матрица", year=1999), _release(_MATRIX), _matrix())
        == _matrix()[0]
    )


def test_a_later_film_with_a_shared_year_keeps_the_largest() -> None:
    """Год 2003 у двух файлов, первым фильмом «Перезагрузка» не открывается - не угадываем."""
    release = _release(_MATRIX)
    picture = Picture(title="Матрица: Перезагрузка", year=2003)

    assert collection_part(picture, release, _matrix()) is None
    assert _default_file(_plan(picture.title, 2003, release), release, _matrix()).index == 2


def test_the_last_film_of_a_dilogy_without_years_in_files_keeps_the_largest() -> None:
    picture = Picture(title="Дюна: Часть вторая", year=2024)

    assert collection_part(picture, _release(_DUNE), _dune()) is None


def test_a_release_not_marked_a_collection_keeps_the_largest() -> None:
    picture = Picture(title="Дюна", year=2021)

    assert collection_part(picture, _release(_DUNE, collection=False), _dune()) is None


def test_the_unnumbered_file_opens_a_pack_numbered_from_two() -> None:
    files = [
        TorrFile(index=1, name="Дюна/Дюна.mkv", size=4 * _GIB),
        TorrFile(index=2, name="Дюна/Дюна 2.mkv", size=5 * _GIB),
    ]

    assert collection_part(Picture(title="Дюна", year=2021), _release(_DUNE), files) == files[0]


def test_the_pack_line_names_the_picture_s_file_when_it_is_not_the_largest() -> None:
    files = _dune()
    total = files[0].size + files[1].size

    assert pack_note(files, files[0]) == phrase(
        "playback.picking_picture_file",
        total=2,
        name=files[0].base,
        share=f"{files[0].size / total:.2f}",
    )
    assert pack_note(files, files[1]) == pack_note(files)
