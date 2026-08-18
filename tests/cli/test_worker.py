"""Внутренняя команда ``cast --play-key``: юниту уходит ровно ключ показа."""

from __future__ import annotations

from tests.fakes.scenario import FakeScenario
from torrcast.cli.worker import worker
from torrcast.domain.args import Args


def test_the_unit_key_is_handed_over_as_a_string() -> None:
    show: FakeScenario[str, int] = FakeScenario(result=0)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 0
    assert show.requests == ["movie:кино:1999"]


def test_the_code_of_the_show_is_the_code_of_the_command() -> None:
    show: FakeScenario[str, int] = FakeScenario(result=2)

    assert worker(Args(query=[], play_key="movie:кино:1999"), show) == 2
