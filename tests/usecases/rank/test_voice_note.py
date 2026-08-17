"""Строка о том, из чего выбиралась озвучка; выбора не было - молчим."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.usecases.rank.voice_note import voice_note


def test_a_single_russian_track_is_not_a_choice() -> None:
    """Это не решение, а единственный вариант, и строка про него была бы шумом."""
    assert voice_note(media(tracks=(track(0, "rus", "Дубляж"),)), 0) == ""
    assert voice_note(media(), 0) == ""


def test_two_russian_tracks_say_what_was_taken_and_out_of_how_many() -> None:
    """У «Барби» рядом лежат три русские дорожки, и выбор был молчаливым."""
    tracks = (track(0, "rus", "Дубляж"), track(1, "rus", "MVO"))
    assert voice_note(media(tracks=tracks), 0) == "дорожек rus 2, беру дубляж"


def test_a_foreign_track_over_two_russian_ones_is_named_by_its_language() -> None:
    """Обе русские служебные - это тоже выбор, и назвать его надо языком."""
    tracks = (track(0, "rus", "Дубляж"), track(1, "rus", "MVO"), track(2, "jpn", "Original"))
    assert voice_note(media(tracks=tracks), 2) == "дорожек rus 2, беру японский"


def test_a_number_outside_the_list_says_nothing() -> None:
    tracks = (track(0, "rus", "Дубляж"), track(1, "rus", "MVO"))
    assert voice_note(media(tracks=tracks), 9) == ""
