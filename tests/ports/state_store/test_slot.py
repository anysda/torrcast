"""Слот назначенного хранилища состояния: где оно лежит и кто это назначает."""

from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import Ephemeral, install, store
from torrcast.ports.state_store.slot import Slot


class _Spy:
    def __init__(self) -> None:
        self.saved: list[WatchState] = []

    def load(self) -> WatchState:
        return WatchState()

    def save(self, state: WatchState) -> None:
        self.saved.append(state)


def test_a_fresh_slot_keeps_the_state_in_the_process() -> None:
    """До слова композиционного корня состояние живёт в памяти прогона."""
    slot = Slot()

    assert isinstance(slot.current(), Ephemeral)


def test_the_installed_store_is_what_the_scenarios_get() -> None:
    """Назначенное хранилище и отдаётся: сценарии смотрят в тот же слот."""
    spy = _Spy()
    install(spy)

    whole = store().load()
    store().save(whole)

    assert store() is spy
    assert spy.saved == [whole]
