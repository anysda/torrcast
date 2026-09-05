"""Подключение внешнего мира ленты: слоты обязаны получить ровно то, что дали."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack._state import Grid
from torrcast.usecases.feed_pack.configure import configure

if TYPE_CHECKING:
    from pathlib import Path


def _world() -> dict[str, Any]:
    forgotten: list[Path] = []
    laid: list[tuple[Path, Path]] = []
    swept: list[Path] = []
    raised: list[Any] = []
    return {
        "segment_name": lambda slot: f"кусок{slot}",
        "segment_slot": lambda name: -7,
        "settle_start": lambda *a, **k: (4.0, 4.5),
        "pack_command": lambda *a, **k: ["ffmpeg", "своя"],
        "packer": type("Fake", (), {"start": staticmethod(lambda *a, **k: None)}),
        "forget_flag": forgotten.append,
        "recode_dir": "свой-перекод",
        "lay_head": lambda piece, out: laid.append((piece, out)),
        "remove_tree": swept.append,
        "segment_paths": lambda where: [where / "свой.ts"],
        "clock": time,
        "spawn": raised.append,
        "map_trusted": lambda url: url == "своя",
        "map_lied": lambda url: raised.append(("соврала", url)),
    }


def test_every_slot_takes_its_value_from_the_composition() -> None:
    """Один вызов - и весь внешний мир ленты на месте, ни одного слота мимо."""
    world = _world()

    configure(**world)

    assert _state.segment_name(4) == "кусок4"
    assert _state.segment_slot("v4.ts") == -7
    assert _state.settle_start("src", 1.0) == (4.0, 4.5)
    assert _state.ffmpeg_pack_command() == ["ffmpeg", "своя"]
    assert _state.forget_playing is world["forget_flag"]
    assert _state.RECODE_DIR == "свой-перекод"
    assert _state.lay_head is world["lay_head"]
    assert _state.Packer is world["packer"]
    assert _state.remove_tree is world["remove_tree"]
    assert _state.segment_paths is world["segment_paths"]
    assert _state.clock_port is world["clock"]
    assert _state.spawn is world["spawn"]
    assert _state.map_trusted is world["map_trusted"]
    assert _state.map_lied is world["map_lied"]


def test_a_second_call_replaces_the_world_and_does_not_mix_two() -> None:
    """Повторное подключение меняет мир целиком: половинчатая замена - это два мира разом."""
    second = dict(_world())
    second["segment_name"] = lambda slot: f"v{slot}"
    second["recode_dir"] = "второй"

    configure(**_world())
    configure(**second)

    assert _state.segment_name(4) == "v4" and _state.RECODE_DIR == "второй"


def test_the_grid_slot_is_not_touched_by_the_composition() -> None:
    """Сетка приходит вызовом, а не подключением: подменять её тут нечем и незачем."""
    configure(**_world())

    assert _state.Grid is Grid
