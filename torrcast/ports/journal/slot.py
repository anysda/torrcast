"""Слот назначенного писателя следа: куда пишется след и кто это назначает."""

from __future__ import annotations

from torrcast.ports.journal.journal import Journal
from torrcast.ports.journal.silent import Silent


class Slot:
    """Куда пишется след этого процесса. До слова корня в слоте лежит молчание."""

    def __init__(self) -> None:
        self._sink: Journal = Silent()

    def current(self) -> Journal:
        """Куда пишется след прямо сейчас."""
        return self._sink

    def install(self, sink: Journal) -> None:
        """Назначить, кто пишет след. Зовёт это только композиционный корень и тесты."""
        self._sink = sink


#: Порт - состояние ПРОЦЕССА, а не объект, который носят по вызовам: слот один на прогон.
_slot = Slot()
#: Прежние имена слоёв: их зовут отовсюду, и функциями они и остаются.
journal = _slot.current
install = _slot.install
