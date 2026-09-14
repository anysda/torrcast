"""Checks fact-flight observer delivery."""

from __future__ import annotations

from torrcast.usecases.tell import tell


def test_tell_lets_a_fact_flight_survive_an_observer_failure() -> None:
    """An observer owns only its callback, not the flight that supplied it."""
    seen: list[str] = []

    def broken() -> None:
        seen.append("called")
        raise RuntimeError("observer failed")

    tell(broken)

    assert seen == ["called"]
