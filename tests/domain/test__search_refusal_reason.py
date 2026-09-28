"""The private search-reason record serializes as the page response needs."""

from __future__ import annotations

from torrcast.domain._search_refusal_reason import _SearchReason


def test_a_reason_serializes_its_key_and_values() -> None:
    assert _SearchReason("web.search.failed", {}).json() == {
        "key": "web.search.failed",
        "values": {},
    }
