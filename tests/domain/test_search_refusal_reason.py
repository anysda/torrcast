"""Search refusal errors become named or generic page reasons."""

from __future__ import annotations

from torrcast.domain.search_refusal_error import SearchRefusalError, SearchRefusalInfraError
from torrcast.domain.search_refusal_reason import reason_of
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


def test_a_named_infrastructure_error_keeps_its_page_reason() -> None:
    refused = SearchRefusalInfraError(
        "discover.prowlarr_not_configured", "web.search.prowlarr_not_configured"
    )

    assert reason_of(refused).key == "web.search.prowlarr_not_configured"
