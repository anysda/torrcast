"""Search refusal errors become named or generic page reasons."""

from __future__ import annotations

from torrcast.domain.search_refusal_error import SearchRefusalError


def test_a_named_error_keeps_its_page_key_and_values() -> None:
    named = SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title="Wednesday",
        season=9,
    )

    assert named.reason.key == "web.search.no_season_releases"
    assert named.reason.values == {"title": "Wednesday", "season": 9}
