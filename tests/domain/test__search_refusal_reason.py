"""The page reason record serializes as the response needs."""

from __future__ import annotations

from torrcast.domain.search_refusal_reason import SearchRefusalReason


def test_a_reason_serializes_its_key_and_values() -> None:
    assert SearchRefusalReason("web.search.failed", {}).json() == {
        "key": "web.search.failed",
        "values": {},
    }
