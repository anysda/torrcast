"""Как назвать язык дорожки вслух; чего в списке нет - «оригинальный»."""

from __future__ import annotations

from tests.usecases.rank.releases import track
from torrcast.usecases.rank.spoken import spoken


def test_a_known_language_is_named_aloud() -> None:
    assert spoken(track(0, "jpn", None)) == "японский"
    assert spoken(track(0, "ENG", None)) == "английский"
    assert spoken(track(0, " fra ", None)) == "французский"


def test_an_unknown_language_is_called_the_original() -> None:
    assert spoken(track(0, "swe", None)) == "оригинальный"
    assert spoken(track(0, None, None)) == "оригинальный"
