"""Гейт дорожки на языке зрителя: у паспорта три ответа, а годен из них только первый."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import media, track
from torrcast.domain.catalogs.tongue import EN, _choose_tongue
from torrcast.usecases.rank.voice_unproven import voice_unproven


@pytest.fixture(autouse=True)
def _russian_gate(_russian_product: None) -> None:
    """Предмет четырёх сценариев ниже - русский гейт: он писан до языкового яруса."""


def test_a_named_russian_track_is_proof() -> None:
    assert not voice_unproven(media(tracks=(track(0, "rus", "Дубляж"),)))


def test_a_foreign_passport_sends_the_release_to_the_bench() -> None:
    foreign = media(tracks=(track(0, "jpn", "Original"),))
    assert voice_unproven(foreign)
    assert voice_unproven(foreign, native=True), "чужой язык назван прямо - справка не спасает"


def test_an_unnamed_track_is_not_a_yes() -> None:
    """🔴 TC-492. Незнание - это не «сойдёт»: «Лэйн» уехала с нерусской дорожкой."""
    unnamed = media(tracks=(track(0, None, None),))
    assert voice_unproven(unnamed)
    assert not voice_unproven(unnamed, native=True), "«Бригаду» никто не озвучивал"


def test_a_passport_without_a_single_track_judges_our_haste_not_the_release() -> None:
    """Это не «язык не назван», а «звук не прочитан» - и бракует оно нашу спешку."""
    assert not voice_unproven(media())


def test_under_english_the_proof_is_an_english_track() -> None:
    """🔴 TC-958. Под английской ручкой гейт ищет английский звук, а не русский.

    Английская дорожка англоязычной картины - оригинал, а не дубляж, и гейту она годна;
    русский дубляж под EN годности не даёт - это не язык зрителя.
    """
    _choose_tongue(EN)
    assert not voice_unproven(media(tracks=(track(0, "eng", "Original"),)))
    assert voice_unproven(media(tracks=(track(0, "rus", "Дубляж"),)))


def test_under_english_the_native_discount_does_not_apply() -> None:
    """Скидка ``native`` - про собственную РУССКУЮ дорожку картины: отечественный фильм
    звучит по-русски, и английскому зрителю безымянная дорожка английского не сулит."""
    _choose_tongue(EN)
    unnamed = media(tracks=(track(0, None, None),))
    assert voice_unproven(unnamed, native=True), "«Бригада» под EN английского звука не имеет"
