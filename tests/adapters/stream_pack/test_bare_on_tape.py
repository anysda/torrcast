"""Голый кусок - перекод или ужатие - встаёт на ленту показа."""

from __future__ import annotations

import struct
from pathlib import Path

from tests.fakes.journal import Tape
from torrcast.adapters.stream_pack.bare_on_tape import bare_on_tape
from torrcast.domain.segment_container import FMP4, MPEGTS
from torrcast.domain.tape_spots import tape_spots

#: Счётчики куска показа, вместо которого уезжает голый: замер живого прогона.
_PICTURE = 956944
_SOUND = 2390016


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _traf(track: int, mark: int) -> bytes:
    tfhd = _box(b"tfhd", struct.pack(">I", 0x020000) + struct.pack(">I", track))
    return _box(b"traf", tfhd + _box(b"tfdt", b"\x01\x00\x00\x00" + struct.pack(">Q", mark)))


def _moof(*trafs: bytes) -> bytes:
    return _box(b"moof", _box(b"mfhd", b"\x00" * 8) + b"".join(trafs))


def _trak(track: int, scale: int, kind: bytes) -> bytes:
    tkhd = _box(b"tkhd", b"\x00" * 12 + struct.pack(">I", track))
    mdhd = _box(b"mdhd", b"\x00" * 12 + struct.pack(">I", scale))
    return _box(b"trak", tkhd + _box(b"mdia", mdhd + _box(b"hdlr", b"\x00" * 8 + kind)))


def _head(where: Path, name: str, picture: int = 16000) -> Path:
    """Заголовок прогона: по нему у голого куска узнают шкалы его дорожек."""
    path = where / name
    path.write_bytes(
        _box(b"ftyp", b"iso6")
        + _box(b"moov", _trak(1, picture, b"vide") + _trak(2, 48000, b"soun"))
    )
    return path


def _bare(where: Path, name: str = "spare9.m4s", picture: int = 1024, sound: int = 1024) -> Path:
    """Перекод или ужатие, как их оставил свой прогон ffmpeg: ``moof mdat`` и счёт с нуля."""
    path = where / name
    path.write_bytes(_moof(_traf(1, picture), _traf(2, sound)) + _box(b"mdat", b"x" * 64))
    return path


def _tape(where: Path, name: str = "v9.m4s") -> Path:
    """Копия этого же места: её счётчики - продолжение счётчиков соседей."""
    path = where / name
    path.write_bytes(_moof(_traf(1, _PICTURE), _traf(2, _SOUND)) + _box(b"mdat", b"z" * 128))
    return path


def _marks(piece: Path) -> list[tuple[int, int]]:
    return [(spot.track, spot.mark) for spot in tape_spots(piece.read_bytes())]


def _heads(where: Path) -> tuple[Path, Path]:
    return _head(where, "spare-init.mp4"), _head(where, "init.mp4")


def test_the_recode_takes_the_counters_of_the_piece_it_goes_out_instead_of(tmp_path: Path) -> None:
    """🔴 Ради этого написано: перекод несёт счётчик своего захода, а не ленту показа.

    Замер базы: у уехавшего зрителю перекода тик 1024 там, где лента показа стоит на
    2868224, - прыжок на 59 с ровно в месте голодания приёмника.
    """
    chunk, tape = _bare(tmp_path), _tape(tmp_path)

    assert bare_on_tape(chunk, tape, 9, "перекод", FMP4, _heads(tmp_path))
    assert _marks(chunk) == [(1, _PICTURE), (2, _SOUND)]


def test_each_track_moves_by_its_own_step(tmp_path: Path) -> None:
    """🔴 Лент две, и у дорожек свой не только счёт, но и ноль: одной поправкой их не свести.

    На живом куске звук стоял на 49.792, а картинка того же куска - на 59.809.
    """
    chunk, tape = _bare(tmp_path, picture=4096, sound=1024), _tape(tmp_path)

    bare_on_tape(chunk, tape, 9, "ужатие", FMP4, _heads(tmp_path))

    assert _marks(chunk) == [(1, _PICTURE), (2, _SOUND)]


def test_not_a_single_byte_of_the_samples_moves(tmp_path: Path) -> None:
    """Счётчик правится на месте, в свою ширину: за ним лежат смещения ``trun``."""
    chunk, tape = _bare(tmp_path), _tape(tmp_path)
    was = chunk.stat().st_size

    bare_on_tape(chunk, tape, 9, "перекод", FMP4, _heads(tmp_path))

    assert chunk.stat().st_size == was and b"x" * 64 in chunk.read_bytes()


def test_a_chunk_written_in_another_scale_is_not_touched_at_all(tmp_path: Path, tape: Tape) -> None:
    """🔴 Кусок уезжает со СВОИМ заголовком, и чужая шкала увела бы весь хвост показа.

    Замер: тот же ffmpeg пишет показ шкалой 16000, а свой заход - 12288, и счётчик,
    перенесённый между ними как есть, увёл бы картинку на 0.768 её места.
    """
    chunk, piece = _bare(tmp_path), _tape(tmp_path)
    heads = _head(tmp_path, "spare-init.mp4", picture=12288), _head(tmp_path, "init.mp4")
    was = chunk.read_bytes()

    assert not bare_on_tape(chunk, piece, 9, "перекод", FMP4, heads)
    assert chunk.read_bytes() == was
    assert tape.named("перекод не поставить на ленту показа") == [{"слот": 9}]


def test_the_refusal_names_the_path_it_came_from(tmp_path: Path, tape: Tape) -> None:
    """Отказ лечится у каждого пути свой, поэтому и называет он путь, а не «кусок»."""
    chunk = _bare(tmp_path)

    bare_on_tape(chunk, tmp_path / "нет.m4s", 4, "ужатие", FMP4, _heads(tmp_path))

    assert tape.named("ужатие не поставить на ленту показа") == [{"слот": 4}]


def test_on_mpegts_the_counters_are_not_touched(tmp_path: Path) -> None:
    """У mpegts метки - время фильма, а не счёт прогона: править там нечего."""
    chunk, piece = _bare(tmp_path), _tape(tmp_path)
    was = chunk.read_bytes()

    assert bare_on_tape(chunk, piece, 9, "перекод", MPEGTS, _heads(tmp_path))
    assert chunk.read_bytes() == was
