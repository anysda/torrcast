"""Уборка позади показа: окно назад остаётся, а всё, что старше, уходит из памяти."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.adapters.recode.grids import grid
from torrcast.adapters.recode.sweep_spare import sweep_spare

if TYPE_CHECKING:
    from pathlib import Path


def test_only_the_pieces_behind_the_show_are_swept_out_of_ram(tmp_path: Path) -> None:
    """Позади показа держим окно, а не выбрасываем всё: перемотка назад бывает короткой."""
    lines = grid()
    for slot in (0, 1, 20):
        (tmp_path / f"v{slot}.ts").write_bytes(b"x" * 1000)
    done = {0, 1, 20}

    # слоты по 10 с: окно в 30 с оставляет всё, что ближе 17-го
    sweep_spare(tmp_path, lines, 200.0, done)

    assert not (tmp_path / "v0.ts").exists() and not (tmp_path / "v1.ts").exists()
    assert (tmp_path / "v20.ts").exists(), "то, что впереди показа, уборке не подлежит"
    assert done == {20}, "выброшенный кусок перестаёт числиться готовым"
