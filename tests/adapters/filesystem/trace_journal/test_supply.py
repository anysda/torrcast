"""Зеркало события снабжения исходником из роя."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.supply import supply


def test_supply_carries_both_rates_the_ratio_and_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = caught(monkeypatch)

    supply(0.375, 3.333, 8.888, False)

    assert seen == [
        (
            "play",
            "supply",
            {"ratio": 0.38, "got": 3.33, "need": 8.89, "enough": False},
        )
    ]
