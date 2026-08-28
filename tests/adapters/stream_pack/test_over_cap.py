"""Зеркало :mod:`torrcast.adapters.stream_pack.over_cap`: последний гейт веса."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.over_cap import over_cap

if TYPE_CHECKING:
    from pathlib import Path


def test_the_caller_chooses_how_a_missing_piece_crosses_the_gate(tmp_path: Path) -> None:
    """До ужатия пропажа безопасна, после обещанного ужатия означает перевес."""
    missing = tmp_path / "missing.ts"

    assert over_cap(missing, 10) is False
    assert over_cap(missing, 10, missing=True) is True


def test_only_a_piece_heavier_than_the_cap_is_over_it(tmp_path: Path) -> None:
    """Ровно потолок ещё допустим, первый лишний байт уже нет."""
    piece = tmp_path / "v1.ts"
    piece.write_bytes(b"x" * 10)

    assert over_cap(piece, 10) is False
    assert over_cap(piece, 9) is True
