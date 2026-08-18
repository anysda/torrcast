"""Слоты внешнего мира ленты: их заполняет композиция, читают все модули пакета."""

from __future__ import annotations

import time

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.feed_grid import FeedGrid

#: Что композиция обязана положить в слоты (:func:`torrcast.usecases.feed_pack.configure`).
FILLED = (
    "segment_name",
    "segment_slot",
    "pack_start",
    "ffmpeg_pack_command",
    "Packer",
    "forget_playing",
    "RECODE_DIR",
    "remove_tree",
    "segment_paths",
)


def test_every_slot_the_composition_fills_is_declared_here() -> None:
    """Слот объявлен именно тут: иначе подмена уехала бы в никуда, а тайпчек смолчал."""
    for name in FILLED:
        assert name in _state.__annotations__, f"слот {name} потерян"


def test_the_grid_of_the_feed_is_the_port_protocol() -> None:
    """Сетка ленты - это протокол порта, а не класс адаптера: слой держит договор."""
    assert _state.Grid is FeedGrid


def test_the_slots_are_wired_by_the_application() -> None:
    """Живое приложение уже заполнило слоты: имена кусков и каталог перекода на месте."""
    assert _state.segment_name(3) == "v3.ts"
    assert _state.segment_slot("v3.ts") == 3
    assert _state.segment_slot("mix3.ts") == -1
    assert isinstance(_state.RECODE_DIR, str) and _state.RECODE_DIR
    assert callable(_state.pack_start) and callable(_state.ffmpeg_pack_command)
    assert callable(_state.forget_playing)
    assert callable(_state.remove_tree) and callable(_state.segment_paths)
    assert hasattr(_state.Packer, "start"), "завод прогона упаковки не встал в слот"


def test_the_clock_of_the_feed_is_the_real_one() -> None:
    """Часы названы импортом, а не слотом: поле ленты берёт ``monotonic`` на сборке.

    Слотом их не сделать: :class:`torrcast.usecases.feed_pack.feed_state._State` кладёт
    ``monotonic`` в ``default_factory`` на импорте, то есть раньше любой композиции.
    """
    assert _state.clock_port is time
