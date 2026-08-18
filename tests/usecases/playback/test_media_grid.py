"""Зеркало договора о сетке: настоящая сетка адаптера обязана ему отвечать целиком."""

from __future__ import annotations

from tests.usecases.playback.world import grid
from torrcast.usecases.playback.media_grid import MediaGrid


def test_the_real_grid_answers_the_named_contract() -> None:
    """Показ зовёт сетку по своему договору - и настоящая сетка отвечает на каждый вопрос."""
    named: MediaGrid = grid(duration=300.0, gop=2.0, step=10.0)

    assert named.count == 30
    assert named.duration == 300.0
    assert named.on_keys is True
    assert named.span(0) == 10.0
    assert named.start(1) == 10.0
    assert named.end(1) == 20.0
    assert named.slot_at(35.0) == 3
    assert named.after(35.0) == 40.0
    assert named.manifest().startswith("#EXTM3U")


def test_the_pointer_of_the_receiver_lands_on_a_boundary() -> None:
    """Ручка прыжка приёмника отдаёт границу КУСКА, а не произвольную секунду."""
    named: MediaGrid = grid()
    bounds = {named.start(slot) for slot in range(named.count)}

    assert named.after(35.0) in bounds
    assert named.after(35.0) > 35.0
