"""Приёмник, который спотыкается о СЕТКУ, а не о секунды.

Называет ему сетку показ (:func:`_play`) - каждой серии свою.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class _Cuttable(Protocol):
    """Приёмник, который спотыкается о СЕТКУ, а не о секунды.

    Отдельно от :class:`torrcast.ports.receiver.Receiver` намеренно, и ровно по той же
    причине, что и :class:`torrcast.usecases.choice._Revivable`: и прыжок сторожа подвиса,
    и подъём после отказа обязаны мерить кусками (:meth:`torrcast.cast.ChromecastReceiver.
    _nudge`), а у приёмника, который так не умеет, границ сетки нет и спрашивать их
    незачем. Сетка у каждой серии своя, поэтому её называют каждой.
    """

    next_cut: Callable[[float], float] | None
