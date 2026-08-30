"""Список озвучек с пометками «дефолт» и «запомнено»."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.domain.release import Release
from torrcast.usecases.rank.voices_table import voices_table


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские пометки таблицы озвучек, писанные до языкового яруса."""


DUB = track(0, "rus", "Дубляж")
ORIG = track(1, "eng", "Original")


def test_the_table_numbers_the_tracks_and_marks_the_default() -> None:
    lines = voices_table(media(tracks=(DUB, ORIG)), default=0).splitlines()

    assert lines == ["Озвучка:", f"  1. {DUB.label}   [дефолт]", f"  2. {ORIG.label}"]


def test_the_remembered_track_gets_its_own_mark() -> None:
    lines = voices_table(media(tracks=(DUB, ORIG)), default=0, remembered=ORIG.label).splitlines()

    assert lines[2] == f"  2. {ORIG.label}   [запомнено]"


def test_one_track_can_carry_both_marks() -> None:
    lines = voices_table(media(tracks=(DUB, ORIG)), default=0, remembered=DUB.label).splitlines()

    assert lines[1] == f"  1. {DUB.label}   [дефолт, запомнено]"


def test_the_table_names_a_studio_known_only_from_the_release() -> None:
    pack = Release(raw_name="Сериал S05 WEB-DL, 2 x MVO (TVShows, NewStation)", title="Сериал")
    tracks = (track(0, "rus", None), track(1, "rus", None))

    lines = voices_table(media(tracks=tracks), 0, studios=pack.studios).splitlines()

    assert lines[1:3] == ["  1. rus (TVShows)   [дефолт]", "  2. rus (NewStation)"]
