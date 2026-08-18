"""Зеркало договора о приёмнике, который спотыкается о сетку, а не о секунды."""

from __future__ import annotations

from collections.abc import Callable

from tests.usecases.playback.world import grid
from torrcast.usecases.playback._cuttable import _Cuttable


class _Cutting:
    """Приёмник, который умеет мерить кусками: у него есть ручка границы."""

    next_cut: Callable[[float], float] | None = None


class _Plain:
    """Приёмник, который так не умеет: границ сетки ему называть незачем."""


def test_a_receiver_with_the_handle_is_recognised_at_runtime() -> None:
    """Опознаётся договор ПРОВЕРКОЙ, а не верой: показ спрашивает сам приёмник."""
    assert isinstance(_Cutting(), _Cuttable)
    assert not isinstance(_Plain(), _Cuttable)


def test_the_grid_boundary_fits_the_handle() -> None:
    """В ручку кладётся граница сетки, и она отвечает секундой куска, а не произвольной."""
    receiver = _Cutting()

    receiver.next_cut = grid().after

    assert receiver.next_cut is not None
    assert receiver.next_cut(35.0) == 40.0
