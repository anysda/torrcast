"""Зеркало :mod:`torrcast.usecases.warm.segment_end`."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from torrcast.usecases.warm.segment_end import segment_end
from torrcast.usecases.warm.settings import TS_PACKET

VIDEO = 0xE0
AUDIO = 0xC0


def _pts(value: float) -> bytes:
    ticks = round(value * 90_000)
    return bytes(
        (
            0x20 | ((ticks >> 29) & 0x0E) | 1,
            (ticks >> 22) & 0xFF,
            ((ticks >> 14) & 0xFE) | 1,
            (ticks >> 7) & 0xFF,
            ((ticks << 1) & 0xFE) | 1,
        )
    )


def _packet(value: float, kind: int = VIDEO) -> bytes:
    pes = b"\x00\x00\x01" + bytes((kind,)) + b"\x00\x00\x80\x80\x05" + _pts(value)
    return b"\x47\x40\x00\x10" + pes + bytes(TS_PACKET - 4 - len(pes))


def test_the_last_video_mark_is_read_from_the_piece_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "v9.ts"
    path.write_bytes(_packet(99.96) + _packet(100.04))

    assert segment_end(path) == pytest.approx(100.04)


def test_the_sound_track_finishes_the_piece_when_the_picture_ends_earlier(
    tmp_path: Path,
) -> None:
    """🔴 TC-772. Кусок кончается там, где кончилась ПОСЛЕДНЯЯ дорожка, а не картинка.

    У настоящего релиза видеодорожка вправе кончиться раньше контейнера: замер на
    «Kung Fu Panda WEB-DL» - последний кадр на 5521.0 при паспорте 5526.176, звук идёт
    ещё пять секунд. Мера по одной картинке объявляла такой целый хвост оборванным.
    """
    path = tmp_path / "v9.ts"
    path.write_bytes(_packet(95.0, VIDEO) + _packet(99.9, AUDIO) + _packet(100.04, AUDIO))

    assert segment_end(path) == pytest.approx(100.04)


def test_a_piece_without_a_picture_in_its_tail_still_has_an_end(tmp_path: Path) -> None:
    """Хвост из одного звука - не «конец не прочитан».

    Ровно это лежит в последних 64 КиБ у релиза, где картинка кончилась пятью секундами
    раньше: видеопакетов там нет ВОВСЕ, и мера по картинке возвращала ``nan``, то есть
    зритель читал «конец не прочитан» о целом куске.
    """
    path = tmp_path / "v9.ts"
    path.write_bytes(_packet(100.04, AUDIO))

    assert segment_end(path) == pytest.approx(100.04)


def test_an_unreadable_tail_does_not_pretend_to_have_an_end(tmp_path: Path) -> None:
    path = tmp_path / "v9.ts"
    path.write_bytes(b"not a transport stream")

    assert math.isnan(segment_end(path))
