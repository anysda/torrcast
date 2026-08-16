"""Сценарий configure сохраняет названный или найденный телевизор."""

from tests.fakes.configuration_store import FakeConfigurationStore
from tests.fakes.console import FakeConsole
from tests.fakes.receiver_finder import FakeReceiverFinder
from torrcast.domain.receiver_info import ReceiverInfo
from torrcast.usecases.configure import Configure


def test_configure_saves_named_mock_receiver() -> None:
    store = FakeConfigurationStore()
    console = FakeConsole()

    assert Configure(store, FakeReceiverFinder(), console).run("mock") == 0
    assert store.settings.tv == "mock"
    assert store.settings.receiver == "mock"
    assert console.messages == ["ТВ: mock (headless-приёмник, каста наружу нет)"]


def test_configure_selects_discovered_receiver() -> None:
    store = FakeConfigurationStore()
    console = FakeConsole(answers=["1"])
    finder = FakeReceiverFinder([ReceiverInfo("Гостиная", "192.0.2.5")])

    Configure(store, finder, console).run()

    assert store.settings.tv == "192.0.2.5"
    assert console.messages[-1] == "ТВ: Гостиная - 192.0.2.5"
