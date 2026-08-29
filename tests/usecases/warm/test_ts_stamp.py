"""Начало куска MPEG-TS по его голове: PTS видео, PCR запасным, ``nan`` честным."""

from __future__ import annotations

import math

from torrcast.usecases.warm.settings import PCR_CLOCK, PES_CLOCK, TS_PACKET
from torrcast.usecases.warm.ts_stamp import _stamp, ts_stamp


def pts_bytes(seconds: float) -> bytes:
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


def video_packet(seconds: float) -> bytes:
    """Пакет TS с началом PES видео и меткой PTS."""
    head = bytes((0x47, 0x40, 0x11, 0x10))
    pes = b"\x00\x00\x01\xe0\x00\x00\x80\x80\x05" + pts_bytes(seconds)
    return (head + pes).ljust(TS_PACKET, b"\xff")


def pcr_packet(seconds: float) -> bytes:
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


def test_the_start_is_the_pts_of_the_first_video_packet() -> None:
    """Берётся PTS, а не PCR: граница сетки стоит на времени ПОКАЗА опорного кадра."""
    assert ts_stamp(pcr_packet(100.0) + video_packet(101.5)) == 101.5


def test_without_a_video_packet_the_transport_clock_answers() -> None:
    """Пакета видео с меткой в голове нет - отвечают часы транспорта, а не «не знаю»."""
    assert ts_stamp(pcr_packet(42.0) * 3) == 42.0


def test_a_head_that_is_not_aligned_to_packets_is_an_honest_unknown() -> None:
    """Сторож, который бракует по догадке, дороже дефекта: не выровнен - ``nan``."""
    assert math.isnan(ts_stamp(b"\x00" * (TS_PACKET * 2)))


def test_a_head_without_any_mark_at_all_is_an_honest_unknown() -> None:
    """Пакеты есть, меток в них нет: ответ - ``nan``, а не ноль ленты."""
    empty = (bytes((0x47, 0x00, 0x11, 0x10)) + b"\xff").ljust(TS_PACKET, b"\xff")
    assert math.isnan(ts_stamp(empty * 4))


def test_the_stamp_unpacks_the_markers_and_not_the_bytes() -> None:
    """Метка - 33 бита между маркерами: разбор обязан их выбросить, а не сдвинуть."""
    assert _stamp(pts_bytes(3600.25)) == 3600.25
    assert _stamp(pts_bytes(0.0)) == 0.0
