"""Где в куске CMAF кончается заголовок и начинается сам фрагмент."""

from __future__ import annotations

import struct

from torrcast.domain.cmaf_body import cmaf_body


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def test_a_chunk_that_is_already_bare_needs_nothing_cut_off() -> None:
    """Кусок сетки лежит голым ``moof mdat`` - резать у него нечего."""
    assert cmaf_body(_box(b"moof", b"x" * 40) + _box(b"mdat", b"y" * 90)) == 0


def test_a_self_contained_splice_names_the_length_of_its_own_head() -> None:
    """Склейка приезжает от муксера с ``ftyp moov`` впереди - вот докуда её заголовок."""
    head = _box(b"ftyp", b"iso6") + _box(b"moov", b"m" * 200)
    assert cmaf_body(head + _box(b"moof", b"z" * 30)) == len(head)


def test_a_head_longer_than_four_gigabytes_is_read_from_the_wide_field() -> None:
    """У ``mdat`` размер уезжает в 64-битное поле, и мерить голову постоянной длиной нельзя."""
    wide = struct.pack(">I", 1) + b"mdat" + struct.pack(">Q", 24) + b"payload!"
    assert cmaf_body(wide + _box(b"moof")) == len(wide)


def test_something_that_is_not_a_chunk_of_the_show_is_said_to_be_such() -> None:
    """Фрагмента нет вовсе - это не кусок показа, и молчать об этом нельзя."""
    assert cmaf_body(_box(b"ftyp", b"iso6") + _box(b"moov", b"m" * 20)) == -1
    assert cmaf_body(b"") == -1


def test_a_box_that_says_it_is_shorter_than_its_own_header_stops_the_walk() -> None:
    """Размер меньше заголовка - дальше не мусор, а бесконечный шаг на месте."""
    assert cmaf_body(struct.pack(">I", 3) + b"junk" + _box(b"moof")) == -1
