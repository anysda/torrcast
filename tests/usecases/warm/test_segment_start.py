"""Начало уложенного куска по его же голове: PTS видео, PCR запасным, ``nan`` честным."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from torrcast.usecases.warm.segment_start import _stamp, segment_start
from torrcast.usecases.warm.settings import PCR_CLOCK, PES_CLOCK, TS_PACKET

if TYPE_CHECKING:
    from pathlib import Path


def _pts(seconds: float) -> bytes:
    """Пять байт метки PES так, как их пишет муксер: 33 бита вперемешку с маркерами."""
    ticks = round(seconds * PES_CLOCK)
    return bytes(
        (
            0x21 | ((ticks >> 30) & 0x7) << 1,
            (ticks >> 22) & 0xFF,
            0x01 | ((ticks >> 15) & 0x7F) << 1,
            (ticks >> 7) & 0xFF,
            0x01 | (ticks & 0x7F) << 1,
        )
    )


def _video_packet(seconds: float) -> bytes:
    """Пакет TS с началом PES видео и меткой PTS."""
    head = bytes((0x47, 0x40, 0x11, 0x10))
    pes = b"\x00\x00\x01\xe0\x00\x00\x80\x80\x05" + _pts(seconds)
    return (head + pes).ljust(TS_PACKET, b"\xff")


def _pcr_packet(seconds: float) -> bytes:
    """Пакет TS без содержимого, зато с часами транспорта в поле адаптации."""
    base = round(seconds * PCR_CLOCK) // 300
    body = bytes(
        (
            0x07,
            0x10,
            (base >> 25) & 0xFF,
            (base >> 17) & 0xFF,
            (base >> 9) & 0xFF,
            (base >> 1) & 0xFF,
            (base & 0x1) << 7,
            0x00,
        )
    )
    return (bytes((0x47, 0x00, 0x11, 0x20)) + body).ljust(TS_PACKET, b"\xff")


def test_the_start_is_the_pts_of_the_first_video_packet(tmp_path: Path) -> None:
    """Берётся PTS, а не PCR: граница сетки стоит на времени ПОКАЗА опорного кадра."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(_pcr_packet(100.0) + _video_packet(101.5))

    assert segment_start(piece) == 101.5


def test_without_a_video_packet_the_transport_clock_answers(tmp_path: Path) -> None:
    """Пакета видео с меткой в голове нет - отвечают часы транспорта, а не «не знаю»."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(_pcr_packet(42.0) * 3)

    assert segment_start(piece) == 42.0


def test_a_file_that_is_not_aligned_to_packets_is_an_honest_unknown(tmp_path: Path) -> None:
    """Сторож, который бракует по догадке, дороже дефекта: не выровнен - ``nan``."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(b"\x00" * (TS_PACKET * 2))

    assert math.isnan(segment_start(piece))


def test_a_missing_file_is_an_honest_unknown_too(tmp_path: Path) -> None:
    """Файла нет - тоже ``nan``: гадать в любую сторону нельзя."""
    assert math.isnan(segment_start(tmp_path / "нет.ts"))


def test_the_stamp_unpacks_the_markers_and_not_the_bytes() -> None:
    """Метка - 33 бита между маркерами: разбор обязан их выбросить, а не сдвинуть."""
    assert _stamp(_pts(3600.25)) == 3600.25
    assert _stamp(_pts(0.0)) == 0.0
