"""Вес полки: сколько на ней записей и сколько байт - цифра для одного ``cast doctor``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe.shelf_weight import shelf_weight

if TYPE_CHECKING:
    from pathlib import Path


def test_a_missing_shelf_weighs_nothing(tmp_path: Path) -> None:
    """Полки ещё нет - это не беда доктора и не повод падать."""
    assert shelf_weight(tmp_path / "нет") == (0, 0)


def test_the_records_are_counted_and_weighed(tmp_path: Path) -> None:
    """Кэши тихо растут годами, и цифра рядом с потолком - способ заметить это заранее."""
    (tmp_path / "a.json").write_bytes(b"x" * 100)
    (tmp_path / "b.json").write_bytes(b"x" * 50)

    assert shelf_weight(tmp_path) == (2, 150)


def test_only_our_own_records_are_weighed(tmp_path: Path) -> None:
    """Черновики соседних писателей полкой не считаются."""
    (tmp_path / "a.json").write_bytes(b"x" * 100)
    (tmp_path / "a.tmp").write_bytes(b"x" * 1000)
    (tmp_path / "внутри").mkdir()

    assert shelf_weight(tmp_path) == (1, 100)
