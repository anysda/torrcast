"""Слот назначенного хранилища состояния: где оно лежит и кто это назначает."""

from __future__ import annotations

from torrcast.ports.state_store.ephemeral import Ephemeral
from torrcast.ports.state_store.state_store import StateStore


class Slot:
    """Хранилище состояния этого процесса. До слова корня состояние живёт в памяти."""

    def __init__(self) -> None:
        self._store: StateStore = Ephemeral()

    def current(self) -> StateStore:
        """Где состояние хранится прямо сейчас."""
        return self._store

    def install(self, target: StateStore) -> None:
        """Назначить хранилище. Зовёт это композиционный корень и тесты."""
        self._store = target


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
store = _slot.current
install = _slot.install
