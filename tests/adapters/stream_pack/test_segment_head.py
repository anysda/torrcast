"""Вырезанный из куска заголовок: всё до первых данных и ничего сверх того."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.segment_head import segment_head

if TYPE_CHECKING:
    from pathlib import Path


def _box(name: bytes, body: bytes = b"") -> bytes:
    return (len(body) + 8).to_bytes(4, "big") + name + body


def test_the_head_is_everything_before_the_first_media_box(tmp_path: Path) -> None:
    """Заголовок кончается там, где начинаются данные: первая же ``moof`` его закрывает."""
    piece = tmp_path / "v3.m4s"
    head = _box(b"ftyp", b"cmfc") + _box(b"moov", "параметры".encode())
    piece.write_bytes(head + _box(b"moof", "метки".encode()) + _box(b"mdat", "кадры".encode()))

    assert segment_head(piece) == head


def test_a_piece_without_a_head_gives_nothing_rather_than_a_guess(tmp_path: Path) -> None:
    """Голый кусок заголовка не несёт, и выдумывать его нельзя: приёмник разберёт мусор."""
    piece = tmp_path / "v4.m4s"
    piece.write_bytes(_box(b"moof", "метки".encode()) + _box(b"mdat", "кадры".encode()))

    assert segment_head(piece) == b""


def test_a_piece_that_is_not_there_is_not_an_avalanche(tmp_path: Path) -> None:
    """Кусок вымело окном ровно между решением и чтением - это пусто, а не падение."""
    assert segment_head(tmp_path / "нет.m4s") == b""


def test_a_truncated_box_table_ends_the_search(tmp_path: Path) -> None:
    """Недописанный кусок разбирать нечем: размер коробки короче собственной шапки."""
    piece = tmp_path / "v5.m4s"
    piece.write_bytes((4).to_bytes(4, "big") + b"ftyp")

    assert segment_head(piece) == b""
