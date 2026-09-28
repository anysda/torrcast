"""Named search refusals preserve a page key independently of console text."""

from __future__ import annotations

from torrcast.domain.search_refusal_error import SearchRefusalError


def test_a_reason_keeps_the_page_key_and_values() -> None:
    refused = SearchRefusalError(
        "discover.no_season_releases",
        "web.search.no_season_releases",
        title="Wednesday",
        season=9,
    )

    assert (refused.reason.key, refused.reason.values) == (
        "web.search.no_season_releases",
        {"title": "Wednesday", "season": 9},
    )
