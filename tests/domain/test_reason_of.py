"""The page reason comes from a named error or the generic fallback."""

from __future__ import annotations

from torrcast.domain.reason_of import reason_of
from torrcast.domain.search_refusal_error import SearchRefusalError
from torrcast.domain.torrcast_error import TorrcastError


def test_a_named_error_keeps_its_reason_and_an_unknown_one_falls_back() -> None:
    named = SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title="Wednesday",
        season=9,
    )

    assert reason_of(named).key == "web.search.no_season_releases"
    assert reason_of(TorrcastError("offline")).key == "web.search.failed"
