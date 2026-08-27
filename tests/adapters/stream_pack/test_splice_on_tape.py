"""Готовая склейка встаёт на ленту показа: её счётчики - счётчики куска, вместо которого она
уходит."""

from __future__ import annotations

import struct
from pathlib import Path

from torrcast.adapters.stream_pack.splice_on_tape import splice_on_tape
from torrcast.domain.tape_spots import tape_spots


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _traf(track: int, mark: int, *, wide: bool = True) -> bytes:
    tfhd = _box(b"tfhd", struct.pack(">I", 0x020000) + struct.pack(">I", track))
    body = b"\x01\x00\x00\x00" + struct.pack(">Q", mark)
    if not wide:
        body = b"\x00\x00\x00\x00" + struct.pack(">I", mark)
    return _box(b"traf", tfhd + _box(b"tfdt", body))


def _moof(*trafs: bytes) -> bytes:
    return _box(b"moof", _box(b"mfhd", b"\x00" * 8) + b"".join(trafs))


def _trak(track: int, scale: int, kind: bytes) -> bytes:
    tkhd = _box(b"tkhd", b"\x00" * 12 + struct.pack(">I", track))
    mdhd = _box(b"mdhd", b"\x00" * 12 + struct.pack(">I", scale))
    hdlr = _box(b"hdlr", b"\x00" * 8 + kind)
    return _box(b"trak", tkhd + _box(b"mdia", mdhd + hdlr))


def _head(where: Path, name: str, picture: int = 16000) -> Path:
    """Заголовок показа: по нему у голого куска узнают шкалы его дорожек."""
    path = where / name
    path.write_bytes(
        _box(b"ftyp", b"iso6")
        + _box(b"moov", _trak(1, picture, b"vide") + _trak(2, 48000, b"soun"))
    )
    return path


def _splice(where: Path, name: str = "mix9.m4s", picture: int = 16000) -> Path:
    """Склейка, как её собрал муксер: свой заголовок впереди и счёт с нуля."""
    path = where / name
    path.write_bytes(
        _box(b"ftyp", b"iso6")
        + _box(b"moov", _trak(1, picture, b"vide") + _trak(2, 48000, b"soun"))
        + _moof(_traf(1, 0), _traf(2, 0))
        + _box(b"mdat", b"x" * 64)
        + _moof(_traf(1, 512), _traf(2, 1024))
        + _box(b"mdat", b"y" * 32)
    )
    return path


def _tape(where: Path, name: str = "v9.m4s", picture: int = 956944, sound: int = 2390016) -> Path:
    """Кусок, вместо которого уедет склейка: голый ``moof mdat`` своего прогона."""
    path = where / name
    path.write_bytes(_moof(_traf(1, picture), _traf(2, sound)) + _box(b"mdat", b"z" * 128))
    return path


def _marks(piece: Path) -> list[tuple[int, int]]:
    return [(spot.track, spot.mark) for spot in tape_spots(piece.read_bytes())]


def test_the_splice_takes_the_counters_of_the_piece_it_goes_out_instead_of(tmp_path: Path) -> None:
    """🔴 Живой замер: соседи-копии стоят на 2390016, а склейка того же места - на нуле.

    Такой кусок уводит приёмник на 49.8 с назад, в начало ленты прогона, и проверка места не
    пускает его наружу - верно.
    """
    splice, tape, head = _splice(tmp_path), _tape(tmp_path), _head(tmp_path, "init.mp4")

    assert splice_on_tape(splice, tape, head)
    assert _marks(splice)[:2] == [(1, 956944), (2, 2390016)]


def test_every_fragment_of_the_splice_moves_by_the_same_step_of_its_track(tmp_path: Path) -> None:
    """Фрагментов у склейки несколько, и сдвинуть надо все: иначе кусок рвётся посередине."""
    splice, tape, head = _splice(tmp_path), _tape(tmp_path), _head(tmp_path, "init.mp4")

    splice_on_tape(splice, tape, head)

    assert _marks(splice)[2:] == [(1, 956944 + 512), (2, 2390016 + 1024)]


def test_not_a_single_byte_of_the_samples_moves(tmp_path: Path) -> None:
    """Счётчик правится на месте: за ним лежат смещения ``trun``, и файл не переписывается."""
    splice, tape, head = _splice(tmp_path), _tape(tmp_path), _head(tmp_path, "init.mp4")
    was = splice.stat().st_size

    splice_on_tape(splice, tape, head)

    assert splice.stat().st_size == was and b"x" * 64 in splice.read_bytes()


def test_a_splice_written_in_another_scale_does_not_go_out_at_all(tmp_path: Path) -> None:
    """🔴 Замер: показ пишет картинку шкалой 16000, а склейку тот же ffmpeg - 12288.

    Один и тот же счётчик значит в них разное время, и перенесённый как есть увёл бы картинку
    на 0.768 её места. Наружу такая склейка не идёт вовсе.
    """
    splice = _splice(tmp_path, picture=12288)
    tape, head = _tape(tmp_path), _head(tmp_path, "init.mp4", picture=16000)
    was = splice.read_bytes()

    assert not splice_on_tape(splice, tape, head)
    assert splice.read_bytes() == was


def test_without_the_head_of_the_show_the_scales_are_not_guessed(tmp_path: Path) -> None:
    """У голого куска своей шкалы нет: спросить её негде - значит и ставить некуда."""
    splice, tape = _splice(tmp_path), _tape(tmp_path)

    assert not splice_on_tape(splice, tape, None)


def test_a_track_the_tape_knows_nothing_about_stops_the_whole_move(tmp_path: Path) -> None:
    """Дорожки нет у куска, вместо которого уходит склейка - ставить её дорожку не на что."""
    splice, head = _splice(tmp_path), _head(tmp_path, "init.mp4")
    lonely = tmp_path / "v8.m4s"
    lonely.write_bytes(_moof(_traf(1, 956944)) + _box(b"mdat", b"z" * 16))
    was = splice.read_bytes()

    assert not splice_on_tape(splice, lonely, head)
    assert splice.read_bytes() == was


def test_a_counter_that_would_not_fit_leaves_the_splice_untouched(tmp_path: Path) -> None:
    """🔴 Файл, переписанный наполовину, - это кусок, у которого уехала часть дорожки.

    Увидеть такое можно было бы только на приёмнике, поэтому считается всё до первой записи.
    """
    path = tmp_path / "mix5.m4s"
    path.write_bytes(
        _box(b"ftyp", b"iso6")
        + _box(b"moov", _trak(1, 16000, b"vide") + _trak(2, 48000, b"soun"))
        + _moof(_traf(1, 0), _traf(2, 0, wide=False))
        + _box(b"mdat", b"x" * 16)
    )
    tape = _tape(tmp_path, sound=1 << 35)
    was = path.read_bytes()

    assert not splice_on_tape(path, tape, _head(tmp_path, "init.mp4"))
    assert path.read_bytes() == was


def test_a_splice_the_muxer_never_wrote_is_not_invented(tmp_path: Path) -> None:
    """Счётчиков в файле нет вовсе - это не склейка, и переставлять в ней нечего."""
    path = tmp_path / "mix4.m4s"
    path.write_bytes(_box(b"ftyp", b"iso6"))

    assert not splice_on_tape(path, _tape(tmp_path), _head(tmp_path, "init.mp4"))


def test_a_piece_that_is_not_there_is_answered_about_honestly(tmp_path: Path) -> None:
    """Куска нет на диске - это отказ, а не падение выкладки."""
    assert not splice_on_tape(tmp_path / "нет.m4s", _tape(tmp_path), _head(tmp_path, "init.mp4"))
    assert not splice_on_tape(_splice(tmp_path), tmp_path / "нет.m4s", _head(tmp_path, "i.mp4"))
