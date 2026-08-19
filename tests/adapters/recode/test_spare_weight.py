"""Вес перекодированного впрок: по нему кодировщик и засыпает под потолком кэша."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.recode.spare_weight import spare_weight

if TYPE_CHECKING:
    from pathlib import Path


def test_the_weight_counts_every_ready_piece_in_megabytes(tmp_path: Path) -> None:
    """Куски лежат в tmpfs, то есть в памяти, и мера тут одна - их суммарный вес."""
    assert spare_weight(tmp_path) == 0.0

    for slot in (0, 1, 20):
        (tmp_path / f"v{slot}.ts").write_bytes(b"x" * 1000)
    (tmp_path / "run").mkdir()

    assert spare_weight(tmp_path) == 3 * 1000 / 1e6, "считаются куски, а не всё подряд"
