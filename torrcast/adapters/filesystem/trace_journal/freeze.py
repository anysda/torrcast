"""Поле записи ``play/freeze``: подгруз, увиденный ходом указателя, а не словом приёмника.

Зовут её строки экрана (:mod:`torrcast.usecases.revive_playback._screen`), читает ``cast log``.
"""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def freeze(pos: float, lost: float, secs: float, total: float, front: float, state: str) -> None:
    """Подгруз: где встала картинка, сколько плёнки потеряно и было ли чем кормить.

    ``front`` стоит в записи по той же причине, что и у нуджа: неподвижная картинка при
    пустом запасе - это ожидание НАС, а при полном - зависание приёмника, и лечится это
    разным. ``state`` - что приёмник о себе в этот момент говорил: на приставке это
    сплошь ``PLAYING``, и без него запись читалась бы как ребуфер, которым она не была.
    """
    emit(
        "play",
        "freeze",
        pos=round(pos, 1),
        lost=round(lost, 2),
        secs=round(secs, 1),
        total=round(total, 2),
        front=round(front, 1),
        state=state,
    )
