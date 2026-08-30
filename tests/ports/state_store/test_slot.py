"""Слот назначенного хранилища состояния: где оно лежит и кто это назначает."""

import pytest

from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import Slot, install, store


class _Spy:
    def __init__(self) -> None:
        self.saved: list[WatchState] = []

    def load(self) -> WatchState:
        return WatchState()

    def save(self, state: WatchState) -> None:
        self.saved.append(state)


def test_a_fresh_slot_refuses_instead_of_remembering_in_memory() -> None:
    """Пустой слот отказывает вслух, а не уводит закладку зрителя в память.

    Память на месте умолчания молчит дважды: сеанс проходит целиком, отказа нет, а
    продолжить недосмотренное потом нечем. Отказ приходит на первом же обращении к
    состоянию - то есть раньше, чем на экране появится картинка.
    """
    slot = Slot()

    with pytest.raises(RuntimeError, match="not assembled"):
        slot.current()


def test_the_installed_store_is_what_the_scenarios_get() -> None:
    """Назначенное хранилище и отдаётся: сценарии смотрят в тот же слот."""
    spy = _Spy()
    install(spy)

    whole = store().load()
    store().save(whole)

    assert store() is spy
    assert spy.saved == [whole]
