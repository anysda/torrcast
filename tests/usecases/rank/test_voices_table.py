"""Список озвучек с пометками «дефолт» и «запомнено»."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.usecases.rank.voices_table import voices_table

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
