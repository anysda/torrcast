"""Слоты внешнего мира прогрева: их заполняет композиция, читают все модули пакета."""

from __future__ import annotations

import torrcast.usecases.warm._state as _state
from torrcast.ports.warm_environment import WarmGrid

#: Что композиция обязана положить в слоты (:func:`torrcast.usecases.warm.configure`).
FILLED = (
    "segment_name",
    "segment_slot",
    "_hms",
    "Packer",
    "ffmpeg_pack_command",
    "pack_start",
    "AUDIO_MBIT",
    "MAX_SEGMENT_BYTES",
    "TS_OVERHEAD",
    "_environment",
)


def test_every_slot_the_composition_fills_is_declared_here() -> None:
    """Слот объявлен именно тут: иначе подмена уехала бы в никуда, а тайпчек смолчал."""
    for name in FILLED:
        assert name in _state.__annotations__, f"слот {name} потерян"


def test_the_grid_of_the_warming_is_the_port_protocol() -> None:
    """Сетка прогрева - это протокол порта, а не класс адаптера: слой держит договор."""
    assert _state.Grid is WarmGrid


def test_the_slots_are_wired_by_the_application() -> None:
    """Живое приложение уже заполнило слоты: имена кусков и потолки на месте.

    Заполняет их композиционный корень (:func:`torrcast.runtime.wire.wire`) - его зовёт
    ``tests.conftest._wired`` на весь прогон.
    """
    assert _state.segment_name(3) == "v3.ts"
    assert _state.segment_slot("v3.ts") == 3
    assert _state.MAX_SEGMENT_BYTES > 0 and _state.TS_OVERHEAD > 1.0
    assert _state.AUDIO_MBIT > 0 and hasattr(_state.Packer, "start")
