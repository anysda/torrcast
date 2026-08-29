"""Начало голого фрагмента CMAF: счётчик картинки, переведённый шкалой заголовка."""

from __future__ import annotations

import math
import struct
from typing import TYPE_CHECKING

from tests.usecases.warm.test_head_clock import head, trak
from torrcast.usecases.warm.frag_stamp import frag_stamp

if TYPE_CHECKING:
    from pathlib import Path


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def traf(track: int, mark: int) -> bytes:
    """Дорожка фрагмента: её номер в ``tfhd``, её счётчик в ``tfdt``."""
    tfhd = box(b"tfhd", struct.pack(">I", 0x020000) + struct.pack(">I", track))
    tfdt = box(b"tfdt", b"\x01\x00\x00\x00" + struct.pack(">Q", mark))
    return box(b"traf", tfhd + tfdt)


def frag(*trafs: bytes) -> bytes:
    """Голова куска CMAF так, как её кладёт муксер: ``styp``, а следом ``moof``."""
    return box(b"styp", b"msdh") + box(b"moof", box(b"mfhd", b"\x00" * 8) + b"".join(trafs))


def _init(tmp_path: Path) -> Path:
    init = tmp_path / "init.mp4"
    init.write_bytes(head(trak(1, 24000, b"vide"), trak(2, 48000, b"soun")))
    return init


def test_the_counter_is_turned_into_seconds_by_the_scale_of_the_header(tmp_path: Path) -> None:
    """Живой замер: слот 12 несёт ``tfdt`` 575575 при шкале 24000 - это 23.982 с ленты прогона."""
    assert frag_stamp(frag(traf(1, 575575)), _init(tmp_path)) == 575575 / 24000


def test_the_picture_track_answers_and_not_the_first_one_in_the_box(tmp_path: Path) -> None:
    """🔴 У каждой дорожки счётчик свой: живой замер даёт между звуком и картинкой 10.0 с."""
    block = frag(traf(2, 2390016), traf(1, 956944))

    assert frag_stamp(block, _init(tmp_path)) == 956944 / 24000


def test_without_a_header_the_counter_is_a_number_without_a_unit(tmp_path: Path) -> None:
    """Шкала живёт только в ``init.mp4``: нет его - переводить тики не во что, ответ ``nan``."""
    assert math.isnan(frag_stamp(frag(traf(1, 575575)), tmp_path / "нет.mp4"))


def test_a_fragment_without_the_picture_counter_is_an_honest_unknown(tmp_path: Path) -> None:
    """В голове только звук - о картинке тут не сказано ничего, и гадать о ней нельзя."""
    assert math.isnan(frag_stamp(frag(traf(2, 2390016)), _init(tmp_path)))
