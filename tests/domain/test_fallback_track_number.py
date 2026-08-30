"""Отличить нашу запасную подпись дорожки от чужого текста заголовка."""

from __future__ import annotations

from torrcast.domain.fallback_track_number import fallback_track_number


def test_reads_the_fallback_shape() -> None:
    assert fallback_track_number("дорожка 3") == 3


def test_foreign_text_is_not_mistaken_for_the_fallback() -> None:
    assert fallback_track_number("rus · Дубляж (MovieDalen)") is None
    assert fallback_track_number("дорожка N/A") is None
    assert fallback_track_number("") is None
