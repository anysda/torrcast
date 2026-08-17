"""Куда прогреву идти дальше и осталась ли ему работа вовсе.

Зовут нитка прогрева (:func:`_work`) и цепочка серий (:func:`_chain`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _missing(state: _State) -> tuple[int, int] | None:
    """Куда идти прогреву: ``(первый непрогретый, последний слот прогона)``.

    Сначала хвост от места показа, потом голова: обрыв связи бьёт по будущему, а не
    по уже пройденному. Прогон всегда доводится до конца своего участка — это и есть
    «один прогон, один непрерывный звук».
    """
    have = state.vault.slots()
    for first in range(state.began_at, state.grid.count):
        if first not in have:
            return first, state.grid.count - 1
    for first in range(0, state.began_at):
        if first not in have:
            return first, state.began_at - 1
    return None


def _pending(state: _State) -> bool:
    """Осталась ли прогреву работа: непрогретое место или тяжёлый кусок под перекод.

    По этому признаку решается цепочка (:meth:`_chain`), а не по :attr:`done`: фильм
    с местами тяжелее потолка приёмника, которые перекодировать нечем, «готовым» не
    станет никогда - но и работа прогрева на нём кончилась, так что следующая серия
    ждать его не обязана.
    """
    return _missing(state) is not None or bool(state._spots_left())
