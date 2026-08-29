"""С какой секунды и какой ЛЕНТЫ начинается уложенный кусок: разбор и его пометка."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from tests.usecases.warm.test_ts_stamp import pcr_packet, video_packet
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import TS_PACKET

if TYPE_CHECKING:
    from pathlib import Path


def frag(payload: bytes = b"") -> bytes:
    """Голова голого фрагмента CMAF: ``styp``, а следом ``moof`` со счётчиками.

    Настоящий фрагмент тут ни к чему: разбирать его некому, и меряется ровно то, что кусок
    ОПОЗНАН как фрагмент, а не принят за мусор.
    """
    styp = (16).to_bytes(4, "big") + b"styp" + b"msdh" + b"\x00" * 4
    moof = (8 + len(payload)).to_bytes(4, "big") + b"moof" + payload
    return styp + moof


def test_a_transport_piece_is_named_by_the_tape_of_the_movie(tmp_path: Path) -> None:
    """У mpegts метки абсолютные (``-copyts``): начало куска сверяется с сеткой прямо."""
    piece = tmp_path / "v7.ts"
    piece.write_bytes(pcr_packet(100.0) + video_packet(101.5))

    assert segment_start(piece) == (101.5, True)


def test_a_cmaf_piece_is_not_named_by_the_tape_of_the_movie(tmp_path: Path) -> None:
    """🔴 TC-879. Во фрагменте времени фильма нет ни в одном байте, и врать об этом нельзя.

    Вся правка ради того, чтобы «не прочитали» и «этой мерой тут не меряют» перестали быть
    одним ``nan`` на двоих: сторож укладки читал его как «годен», а показ - как «мимо
    сетки». Опознан кусок при этом обязан быть: ``movie`` тут ``False``, а не ``True``.
    """
    piece = tmp_path / "v12.m4s"
    piece.write_bytes(frag())

    began, movie = segment_start(piece)
    assert math.isnan(began)
    assert movie is False, "у фрагмента CMAF нашлось время фильма"


def test_a_bare_fragment_without_its_box_of_kind_is_recognised_too(tmp_path: Path) -> None:
    """Муксер вправе не писать ``styp``: голова с одного ``moof`` - тот же самый случай."""
    piece = tmp_path / "v12.m4s"
    piece.write_bytes((16).to_bytes(4, "big") + b"moof" + b"\x00" * 8)

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
