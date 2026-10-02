"""Затёртый нулями участок куска находится, здоровый кусок чист."""

from __future__ import annotations

from pathlib import Path

from torrcast.usecases.warm.zeroed import CHUNK, ZERO_RUN, zeroed

#: Три пакета настоящего испорченного ``v14.ts`` («Оно» 2017, кадр около 141.2 с): последний
#: здоровый пакет с началом дыры и два пакета, где вся нагрузка - нули. Дыра в 16 КиБ разложена
#: муксером по пакетам, поэтому самый длинный пробег нулей в ней ровно 184 байта. Заголовки и
#: нули взяты как есть, 14 байт картинки перед дырой заменены на ``0xFF``.
REAL_HOLE = Path(__file__).parents[2] / "fixtures" / "zeroed_v14.ts"

#: Пакет TS с полезной нагрузкой без единой полной строки нулей: так выглядит здоровый кусок.
PACKET = b"\x47\x01\x00\x10" + (b"\x00\x00\x03\x01" * 46)


def _piece(tmp_path: Path, body: bytes) -> Path:
    path = tmp_path / "v14.ts"
    path.write_bytes(body)
    return path


def test_a_healthy_piece_is_clean(tmp_path: Path) -> None:
    assert not zeroed(_piece(tmp_path, PACKET * 20000))


def test_the_real_broken_piece_is_found() -> None:
    """Порог не выше настоящей порчи: при 185 детектор слепнет на ней."""
    assert zeroed(REAL_HOLE)


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
