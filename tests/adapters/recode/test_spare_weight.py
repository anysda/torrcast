"""Вес перекодированного впрок: по нему кодировщик и засыпает под потолком кэша."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.recode.spare_weight import spare_weight
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path


def test_the_weight_counts_every_ready_piece_in_megabytes(tmp_path: Path) -> None:
    """Куски лежат в tmpfs, то есть в памяти, и мера тут одна - их суммарный вес."""
    assert spare_weight(tmp_path) == 0.0

    for slot in (0, 1, 20):
        (tmp_path / f"v{slot}.ts").write_bytes(b"x" * 1000)
    (tmp_path / "run").mkdir()

    assert spare_weight(tmp_path) == 3 * 1000 / 1e6, "считаются куски, а не всё подряд"


def test_the_weight_counts_the_pieces_of_the_container_the_receiver_asked_for(
    tmp_path: Path,
) -> None:
    """Считать чужой маской - значит вечно видеть пустой кэш и никогда не заснуть."""
    for slot in (0, 1):
        (tmp_path / f"v{slot}.m4s").write_bytes(b"x" * 1000)

    assert spare_weight(tmp_path, FMP4) == 2 * 1000 / 1e6
    assert spare_weight(tmp_path) == 0.0, "куски чужого контейнера этому кэшу не свои"
