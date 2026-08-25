"""След отданного сегмента: номер, вес, время отдачи, ожидание и источник куска."""

from __future__ import annotations

import time

from torrcast.adapters.http_server.log_segment import log_segment
from torrcast.domain.trace_sources import PACKED
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install


class _Tape(Silent):
    """Лента, которая помнит отданные сегменты: молчание Silent для всего остального."""

    def __init__(self) -> None:
        self.rows: list[tuple[int, float, float, float, str]] = []

    def segment(self, slot: int, mb: float, sent: float, wait: float, src: str) -> None:
        self.rows.append((slot, mb, sent, wait, src))


def test_every_piece_handed_to_the_receiver_names_its_maker(_ports_restored: None) -> None:
    """Показ идёт кусками ДВУХ производителей, и по записи обязано быть видно, чей это."""
    tape = _Tape()
    install(tape)
    began = time.monotonic() - 2.0

    log_segment("v7.ts", began, 3_000_000, 0.5, PACKED)

    (slot, mb, sent, wait, src) = tape.rows[0]
    assert (slot, mb, sent, src) == (7, 3.0, 0.5, PACKED)
    assert wait > 1.0, "ожидание - это всё, кроме самой отдачи по сети"


def test_the_manifest_is_not_a_segment_and_is_never_written(_ports_restored: None) -> None:
    """Манифест дёргается на каждый опрос приёмника - в следе он утопил бы куски."""
    tape = _Tape()
    install(tape)

    log_segment("index.m3u8", time.monotonic(), 1000, 0.1, PACKED)

    assert tape.rows == []


def test_a_piece_of_the_fmp4_container_is_written_to_the_tape_too(_ports_restored: None) -> None:
    """Иначе на CMAF след раздачи пуст, и «подгрузов ноль» читается из слепого прибора."""
    tape = _Tape()
    install(tape)

    log_segment("v7.m4s", time.monotonic(), 3_000_000, 0.5, PACKED)
    log_segment("init.mp4", time.monotonic(), 1345, 0.1, PACKED)

    assert [row[0] for row in tape.rows] == [7], "заголовок контейнера сегментом не считается"
