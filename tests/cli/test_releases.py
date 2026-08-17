"""Ручка ``cast releases``: разобранная строка уходит сценарию как есть."""

from __future__ import annotations

from tests.fakes.scenario import FakeScenario
from torrcast.cli.args import Args
from torrcast.cli.releases import releases


def test_the_parsed_line_reaches_the_scenario_untouched() -> None:
    scenario: FakeScenario[Args, int] = FakeScenario(result=0)
    args = Args(query=["кино"])

    assert releases(args, scenario) == 0
    assert scenario.requests == [args], "аргументы уходят той же записью, а не пересобранной"


def test_the_code_of_the_scenario_is_the_code_of_the_command() -> None:
    scenario: FakeScenario[Args, int] = FakeScenario(result=1)

    assert releases(Args(query=["кино"]), scenario) == 1
