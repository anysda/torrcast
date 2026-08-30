"""Каким языком заговорит файл: язык той дорожки, которую взял бы показ."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.usecases.rank.heard import heard


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские названия языков дорожки, писанные до языкового яруса."""


def test_the_language_is_the_one_the_show_would_play() -> None:
    assert heard(media(tracks=(track(0, "jpn", "Original"),))) == "японский"


def test_an_unnamed_track_is_called_unnamed_not_original() -> None:
    """🔴 TC-492. Придумывать язык там, где гейт бракует релиз, - та же ошибка."""
    assert heard(media(tracks=(track(0, None, None),))) == "не назван"


def test_a_passport_without_tracks_says_so_too() -> None:
    assert heard(media()) == "не назван"


def test_the_default_is_a_field_not_a_place_in_the_list() -> None:
    """Паспорт из кэша приходит со своими номерами, и промах стоит вежливого отката."""
    assert heard(media(tracks=(track(7, "jpn", "Original"),))) == "японский"
