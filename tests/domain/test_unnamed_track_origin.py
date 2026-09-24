"""Единое правило имени для дорожки без языка и заголовка."""

from __future__ import annotations

from tests.usecases.rank.releases import track
from torrcast.domain.unnamed_track_origin import unnamed_track_origin


def test_only_a_lone_fully_unnamed_track_is_named_by_picture_origin() -> None:
    blank = track(0, None, None)

    assert unnamed_track_origin(blank, native=True, lone=True) == "native"
    assert unnamed_track_origin(blank, native=False, lone=True) == "foreign"
    assert unnamed_track_origin(blank, native=True, lone=False) == ""
    assert unnamed_track_origin(track(0, "rus", None), native=True, lone=True) == ""
    assert unnamed_track_origin(track(0, None, "Дубляж"), native=True, lone=True) == ""
