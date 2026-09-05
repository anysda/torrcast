"""Заголовок, который кусок уже несёт в себе, или пусто - когда он голый, как соседи."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.carried_head import carried_head

if TYPE_CHECKING:
    from pathlib import Path


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


#: Голый кусок сетки: ровно то, что кладёт муксер каждым сегментом CMAF.
_BARE = _box(b"moof", b"x" * 40) + _box(b"mdat", b"y" * 90)


def test_a_bare_chunk_carries_nothing_and_says_so(tmp_path: Path) -> None:
    """Такой кусок описан общим заголовком показа, и своего у него нет вовсе."""
    piece = tmp_path / "v1.m4s"
    piece.write_bytes(_BARE)

    assert carried_head(piece) == b""


def test_a_chunk_with_a_head_in_front_gives_back_exactly_that_head(tmp_path: Path) -> None:
    """Ответ обязан быть побайтовым: им сравнивают, сменился ли производитель картинки."""
    head = _box(b"ftyp", b"iso6") + _box(b"moov", b"m" * 300)
    piece = tmp_path / "v2.m4s"
    piece.write_bytes(head + _BARE)

    assert carried_head(piece) == head


def test_a_file_that_is_not_a_chunk_at_all_answers_empty(tmp_path: Path) -> None:
    """Мусор на входе - это «своего заголовка нет», а не заголовок из мусора."""
    piece = tmp_path / "v3.m4s"
    piece.write_bytes(b"not a chunk at all")

    assert carried_head(piece) == b""


def test_a_missing_chunk_answers_empty_instead_of_falling(tmp_path: Path) -> None:
    """Соседа слева может не быть вовсе - на перемотке это обычное дело, а не авария."""
    assert carried_head(tmp_path / "v4.m4s") == b""
