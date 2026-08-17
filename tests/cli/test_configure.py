"""Команда ``cast --tv``: адрес из строки или меню, но всегда - один сценарий настройки."""

from __future__ import annotations

from tests.fakes.scenario import FakeScenario
from torrcast.cli.args import Args
from torrcast.cli.configure import configure
from torrcast.cli.parse_args import TV_MENU


def test_a_named_address_reaches_the_scenario_as_it_was_typed() -> None:
    settings: FakeScenario[str | None, int] = FakeScenario(result=0)

    assert configure(Args(query=[], tv="10.0.0.50"), settings) == 0
    assert settings.requests == ["10.0.0.50"]


def test_tv_without_an_address_asks_the_scenario_to_look_around() -> None:
    """``--tv`` без адреса - это меню: вместо строки-заглушки сценарий получает ``None``."""
    settings: FakeScenario[str | None, int] = FakeScenario(result=0)

    assert configure(Args(query=[], tv=TV_MENU), settings) == 0
    assert settings.requests == [None]


def test_the_code_of_the_scenario_is_the_code_of_the_command() -> None:
    settings: FakeScenario[str | None, int] = FakeScenario(result=1)

    assert configure(Args(query=[], tv="mock"), settings) == 1
