"""Общий заголовок показа: кладётся один раз, целиком и из любого куска."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.lay_head import lay_head

if TYPE_CHECKING:
    from pathlib import Path


def _box(name: bytes, body: bytes = b"") -> bytes:
    return (len(body) + 8).to_bytes(4, "big") + name + body


def _piece(where: Path, name: str, mark: bytes) -> Path:
    piece = where / name
    piece.write_bytes(_box(b"ftyp", b"cmfc") + _box(b"moov", mark) + _box(b"moof", "м".encode()))
    return piece


def test_the_head_of_the_show_is_laid_out_once(tmp_path: Path) -> None:
    """Второй кусок заголовок не переписывает: приёмник взял его на старте показа."""
    out = tmp_path / "out"
    out.mkdir()

    lay_head(_piece(out, "v0.m4s", "первый".encode()), out)
    lay_head(_piece(out, "v1.m4s", "второй".encode()), out)

    assert "первый".encode() in (out / "init.mp4").read_bytes()
    assert "второй".encode() not in (out / "init.mp4").read_bytes()


def test_nothing_half_written_is_left_next_to_the_head(tmp_path: Path) -> None:
    """Приёмник читает заголовок один раз: недописанный стоил бы ему всего показа."""
    out = tmp_path / "out"
    out.mkdir()

    lay_head(_piece(out, "v0.m4s", "параметры".encode()), out)

    assert (out / "init.mp4").exists()
    assert not (out / "init.mp4.part").exists()


def test_a_piece_without_a_head_leaves_the_show_without_one(tmp_path: Path) -> None:
    """Выдумывать заголовок нельзя: лучше его отсутствие, чем чужие параметры."""
    out = tmp_path / "out"
    out.mkdir()
    bare = out / "v0.m4s"
    bare.write_bytes(_box(b"moof", "м".encode()) + _box(b"mdat", "к".encode()))

    lay_head(bare, out)

    assert not (out / "init.mp4").exists()
