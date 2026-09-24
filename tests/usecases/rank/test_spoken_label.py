"""Подпись дорожки вслух; ключ памяти под ней не двигается ни на байт."""

from __future__ import annotations

from tests.usecases.rank.releases import track
from torrcast.usecases.rank.spoken_label import spoken_label


def test_fallback_label_speaks_the_product_language(_english: None) -> None:
    assert spoken_label(track(0, None, None)) == "track 1"


def test_a_release_titled_track_keeps_its_own_words(_english: None) -> None:
    # «Дубляж (MovieDalen)» - надпись самой раздачи, а не наше слово: переводу не подлежит.
    assert spoken_label(track(1, "rus", "Дубляж (MovieDalen)")) == "rus · Дубляж (MovieDalen)"


def test_a_lone_unnamed_native_track_is_russian_on_both_product_languages(
    _english: None,
) -> None:
    blank = track(0, None, None)

    assert spoken_label(blank, native=True, lone=True) == "Russian"


def test_a_lone_unnamed_foreign_track_says_its_language_was_not_stated(
    _english: None,
) -> None:
    blank = track(0, None, None)

    assert spoken_label(blank, native=False, lone=True) == "language not stated"


def test_a_named_russian_track_keeps_its_release_label(_english: None) -> None:
    assert spoken_label(track(0, "rus", None), native=True, lone=True) == "rus"
