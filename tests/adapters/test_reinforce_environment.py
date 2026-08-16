"""Проверяет системную среду уточнения."""

from typing import Any, cast

from torrcast.adapters.reinforce_environment import environment


def test_reinforce_environment_exposes_fact() -> None:
    assert cast(Any, environment.fact_type).__name__ == "Fact"
