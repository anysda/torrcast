"""Состояние просмотра за портом хранилища: имена договора поверх того же файла.

Заводит его композиционный корень (:mod:`torrcast.runtime.wire`) и раздаёт сценариям."""

from __future__ import annotations

from torrcast.adapters.filesystem.state.state import State
from torrcast.domain.watch_state import WatchState


class FileStateStore:
    """Состояние просмотра в файле: за портом :class:`~torrcast.ports.state_store.StateStore`.

    Своего кода тут нет ни строчки - чтение и атомарная запись живут в :class:`State`,
    а этот класс только называет их именами договора. Заводится он один на процесс и
    состояния в себе не держит: каждый :meth:`load` перечитывает файл, потому что рядом
    пишет другой ход показа.
    """

    def load(self) -> WatchState:
        """Прочитать состояние целиком."""
        return State.load()

    def save(self, state: WatchState) -> None:
        """Записать состояние целиком, атомарно.

        Пишет его :meth:`State.save`, а не своя раскладка того же файла: две раскладки
        разошлись бы молча, и половина показа читала бы одно, а половина писала другое.
        """
        State(state.entries).save()
