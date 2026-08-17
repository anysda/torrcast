"""Гейт русской дорожки: у паспорта три ответа, а годен из них только первый."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.usecases.rank.voice_unproven import voice_unproven


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
