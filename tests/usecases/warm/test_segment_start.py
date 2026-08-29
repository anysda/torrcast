"""С какой секунды и какой ЛЕНТЫ начинается уложенный кусок: разбор и его пометка."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from tests.usecases.warm.test_frag_stamp import frag, traf
from tests.usecases.warm.test_head_clock import head, trak
from tests.usecases.warm.test_ts_stamp import pcr_packet, video_packet
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import TS_PACKET

if TYPE_CHECKING:
    from pathlib import Path


def test_a_transport_piece_is_named_by_the_tape_of_the_movie(tmp_path: Path) -> None:
    """У mpegts метки абсолютные (``-copyts``): начало куска сверяется с сеткой прямо."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(pcr_packet(100.0) + video_packet(101.5))

    assert segment_start(piece) == (101.5, True)


def test_a_cmaf_piece_is_named_by_the_tape_of_the_run(tmp_path: Path) -> None:
    """🔴 TC-879. Во фрагменте стоит счётчик прогона муксера, и сверять его с сеткой нельзя.

    Число тут читается честное, но лента у него другая, и вся правка ради того, чтобы эти
    два случая перестали быть одним ``nan`` на двоих.
    """
    (tmp_path / "init.mp4").write_bytes(head(trak(1, 24000, b"vide")))
    piece = tmp_path / "v12.m4s"
    piece.write_bytes(frag(traf(1, 575575)))

    began, movie = segment_start(piece)
    assert began == 575575 / 24000
    assert movie is False, "счётчик прогона выдан за время фильма"


def test_an_unreadable_cmaf_piece_is_not_the_tape_of_the_movie_either(tmp_path: Path) -> None:
    """Заголовка рядом нет: и числа нет, и ленты фильма тут не появилось."""
    piece = tmp_path / "v12.m4s"
    piece.write_bytes(frag(traf(1, 575575)))

    began, movie = segment_start(piece)
    assert math.isnan(began) and movie is False


def test_a_file_that_is_not_aligned_to_packets_is_an_honest_unknown(tmp_path: Path) -> None:
    """Сторож, который бракует по догадке, дороже дефекта: не выровнен - ``nan``."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(b"\x47" + b"\x00" * (TS_PACKET * 2))

    assert math.isnan(segment_start(piece).began)


def test_a_file_that_is_neither_packets_nor_boxes_is_an_honest_unknown(tmp_path: Path) -> None:
    """Ни пакетов TS, ни боксов MP4: разбирать нечего, и приговора у нас тут нет."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(b"\x00" * (TS_PACKET * 2))

    began, movie = segment_start(piece)
    assert math.isnan(began) and movie is True


def test_a_missing_file_is_an_honest_unknown_too(tmp_path: Path) -> None:
    """Файла нет - тоже ``nan``: гадать в любую сторону нельзя."""
    assert math.isnan(segment_start(tmp_path / "нет.ts").began)
