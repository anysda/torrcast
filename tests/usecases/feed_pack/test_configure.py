"""Подключение внешнего мира ленты: слоты обязаны получить ровно то, что дали."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack._state import Grid
from torrcast.usecases.feed_pack.configure import configure

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

SLOTS = (
    "segment_name",
    "segment_slot",
    "pack_start",
    "ffmpeg_pack_command",
    "forget_playing",
    "RECODE_DIR",
)


def _restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """Вернуть боевые слоты после теста: они общие на весь прогон."""
    for name in SLOTS:
        monkeypatch.setattr(_state, name, getattr(_state, name), raising=False)


def _world() -> dict[str, Any]:
    forgotten: list[Path] = []
    return {
        "segment_name": lambda slot: f"кусок{slot}",
        "segment_slot": lambda name: -7,
        "pack_start": lambda *a, **k: 4.5,
        "pack_command": lambda *a, **k: ["ffmpeg", "своя"],
        "forget_flag": forgotten.append,
        "recode_dir": "свой-перекод",
    }


def test_every_slot_takes_its_value_from_the_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Один вызов - и весь внешний мир ленты на месте, ни одного слота мимо."""
    _restore(monkeypatch)
    world = _world()

    configure(**world)

    assert _state.segment_name(4) == "кусок4"
    assert _state.segment_slot("v4.ts") == -7
    assert _state.pack_start("src", 1.0) == 4.5
    assert _state.ffmpeg_pack_command() == ["ffmpeg", "своя"]
    assert _state.forget_playing is world["forget_flag"]
    assert _state.RECODE_DIR == "свой-перекод"


def test_a_second_call_replaces_the_world_and_does_not_mix_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Повторное подключение меняет мир целиком: половинчатая замена - это два мира разом."""
    _restore(monkeypatch)
    second = dict(_world())
    second["segment_name"] = lambda slot: f"v{slot}"
    second["recode_dir"] = "второй"

    configure(**_world())
    configure(**second)

    assert _state.segment_name(4) == "v4" and _state.RECODE_DIR == "второй"


def test_the_grid_slot_is_not_touched_by_the_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сетка приходит вызовом, а не подключением: подменять её тут нечем и незачем."""
    _restore(monkeypatch)

    configure(**_world())

    assert _state.Grid is Grid
