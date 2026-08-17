"""Дорожка, которая заиграет по умолчанию, идёт без метки языка."""

from __future__ import annotations

from tests.usecases.rank.releases import media, track
from torrcast.usecases.rank.default_unnamed import default_unnamed


def test_an_unnamed_default_is_named_so() -> None:
    assert default_unnamed(media(tracks=(track(0, None, None),)))
    assert not default_unnamed(media(tracks=(track(0, "rus", "Дубляж"),)))


def test_an_index_out_of_place_falls_back_politely() -> None:
    """🔴 Иначе это ``IndexError`` посреди запуска показа, а не вежливый откат."""
    assert default_unnamed(media(tracks=(track(7, None, None),)))


def test_a_passport_without_tracks_has_no_unnamed_default() -> None:
    assert not default_unnamed(media())
