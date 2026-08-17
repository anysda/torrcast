"""Честная строка про звук, когда русской дорожки в файле не оказалось."""

from __future__ import annotations

from tests.usecases.rank.releases import media, rel, track
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.rank.sound_note import sound_note

JAP = track(0, "jpn", "Original")
UNNAMED = track(0, None, None)
DUBBED = "Соседняя (1999) BDRip 1080p | Дубляж"


def test_a_russian_track_in_the_file_means_no_line() -> None:
    assert sound_note(media(tracks=(track(0, "rus", "Дубляж"),)), 0, []) == ""


def test_a_translation_in_another_release_is_named_with_a_way_out() -> None:
    pool = [rel(name=DUBBED, title="Соседняя", seeders=10)]
    assert sound_note(media(tracks=(JAP,)), 0, pool) == (
        "только японский звук - в каталоге, возможно, есть перевод в другой раздаче"
    )


def test_a_translation_lying_in_a_separate_file_says_there_is_nothing_to_pick() -> None:
    """🔴 TC-191. Играть звук из соседнего файла показ не умеет, и честнее сказать прямо."""
    files = (TorrFile(index=0, name="Кино/rus.mka", size=1 << 20),)
    assert sound_note(media(tracks=(JAP,)), 0, [], files=files) == (
        "только японский звук - в каталоге перевод есть, но лежит отдельным файлом"
    )


def test_no_translation_anywhere_is_said_plainly() -> None:
    assert sound_note(media(tracks=(JAP,)), 0, []) == (
        "только японский звук, перевода в каталоге нет"
    )


def test_an_unnamed_track_leans_on_the_name_only_to_name_the_source() -> None:
    """Улику надо НАЗВАТЬ, а не молча подставить русскую и не выдать за неё."""
    dubbed = rel(name="Кино (1999) BDRip 1080p | Дубляж")
    assert sound_note(media(tracks=(UNNAMED,)), 0, [], release=dubbed) == (
        "звук без метки языка - по имени релиза русская"
    )
    assert sound_note(media(tracks=(UNNAMED,)), 0, []) == (
        "язык дорожки неизвестен - раздача не назвала язык озвучки"
    )
    assert sound_note(media(tracks=(UNNAMED,)), 0, [], native=True) == ""
