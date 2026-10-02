"""Затёртый нулями участок куска находится, здоровый кусок чист."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.warm.zeroed import CHUNK, ZERO_RUN, zeroed

if TYPE_CHECKING:
    from pathlib import Path

#: Пакет TS с полезной нагрузкой без единой полной строки нулей: так выглядит здоровый кусок.
PACKET = b"\x47\x01\x00\x10" + (b"\x00\x00\x03\x01" * 46)


def _piece(tmp_path: Path, body: bytes) -> Path:
    path = tmp_path / "v14.ts"
    path.write_bytes(body)
    return path


def test_a_healthy_piece_is_clean(tmp_path: Path) -> None:
    assert not zeroed(_piece(tmp_path, PACKET * 20000))


def test_a_zeroed_block_inside_the_picture_is_found(tmp_path: Path) -> None:
    """16 КиБ нулей, разложенные муксером по пакетам: целая нагрузка пакета из нулей."""
    hole = b"".join(b"\x47\x01\x00\x10" + b"\x00" * ZERO_RUN for _ in range(89))
    assert zeroed(_piece(tmp_path, PACKET * 5000 + hole + PACKET * 5000))


def test_a_run_split_by_the_read_window_is_still_found(tmp_path: Path) -> None:
    lead = b"\x01" * (CHUNK - ZERO_RUN // 2)
    assert zeroed(_piece(tmp_path, lead + b"\x00" * ZERO_RUN + b"\x01" * 64))


def test_a_run_one_byte_short_is_not_a_hole(tmp_path: Path) -> None:
    assert not zeroed(_piece(tmp_path, b"\x01" * 100 + b"\x00" * (ZERO_RUN - 1) + b"\x01"))


def test_an_unreadable_piece_is_not_called_broken(tmp_path: Path) -> None:
    assert not zeroed(tmp_path / "gone.ts")
