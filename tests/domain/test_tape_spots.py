"""Счётчики ленты дорожек внутри куска CMAF: где они лежат и что в них стоит."""

from __future__ import annotations

import struct

from torrcast.domain.tape_spots import tape_spots


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _traf(track: int, mark: int, *, wide: bool = True) -> bytes:
    """Дорожка одного фрагмента: её номер в ``tfhd`` и её счётчик в ``tfdt``."""
    tfhd = _box(b"tfhd", struct.pack(">I", 0x020000) + struct.pack(">I", track))
    body = b"\x01\x00\x00\x00" + struct.pack(">Q", mark)
    if not wide:
        body = b"\x00\x00\x00\x00" + struct.pack(">I", mark)
    return _box(b"traf", tfhd + _box(b"tfdt", body))


def _moof(*trafs: bytes) -> bytes:
    return _box(b"moof", _box(b"mfhd", b"\x00" * 8) + b"".join(trafs))


def test_each_track_of_the_chunk_answers_about_its_own_counter() -> None:
    """🔴 Счётчик у каждой дорожки свой: живой кусок показа несёт звук 2390016, картинку 956944."""
    block = _moof(_traf(1, 956944), _traf(2, 2390016))

    assert [(spot.track, spot.mark) for spot in tape_spots(block)] == [(1, 956944), (2, 2390016)]


def test_the_counter_is_named_by_the_track_of_its_own_box_not_by_its_place() -> None:
    """Порядок дорожек в куске не обещан никем: звук бывает первым, и это не звук картинки."""
    block = _moof(_traf(2, 2390016), _traf(1, 956944))

    assert {spot.track: spot.mark for spot in tape_spots(block)} == {1: 956944, 2: 2390016}


def test_every_fragment_of_the_piece_is_found_not_only_the_first() -> None:
    """У склейки фрагментов несколько, и переписать надо ВСЕ: иначе кусок рвётся посередине."""
    block = _moof(_traf(1, 0)) + _box(b"mdat", b"x" * 40) + _moof(_traf(1, 122880))

    assert [spot.mark for spot in tape_spots(block)] == [0, 122880]


def test_the_offset_of_the_counter_points_into_the_file_itself() -> None:
    """Переписывающий правит счётчик на месте: смещение обязано быть от начала файла."""
    block = _moof(_traf(1, 7))
    (spot,) = tape_spots(block, base=4096)

    assert spot.at > 4096 and struct.unpack(">Q", block[spot.at - 4096 : spot.at - 4088])[0] == 7


def test_a_narrow_counter_is_read_from_its_own_four_bytes() -> None:
    """``tfdt`` версии 0 несёт счётчик вчетверо уже, и прочитать его надо как есть."""
    (spot,) = tape_spots(_moof(_traf(1, 65535, wide=False)))

    assert (spot.mark, spot.width) == (65535, 4)


def test_a_chunk_without_a_single_counter_says_so() -> None:
    """Счётчиков нет - переставлять нечего, и догадываться о них тут не на чем."""
    assert tape_spots(_box(b"ftyp", b"iso6") + _box(b"mdat", b"y" * 20)) == ()


def test_a_box_shorter_than_its_own_header_stops_the_walk() -> None:
    """Размер меньше заголовка - это не мусор дальше, а бесконечный шаг на месте."""
    assert tape_spots(struct.pack(">I", 3) + b"junk" + _moof(_traf(1, 5))) == ()
