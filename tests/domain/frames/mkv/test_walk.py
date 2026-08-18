"""Зеркало :mod:`torrcast.domain.frames.mkv.walk`: дети одного элемента EBML.

Мера про два края обхода. Первый - элемент, который в прочитанный кусок не влез целиком
(``Segment`` длиной с фильм): шагнуть за него вслепую нельзя, там ещё не прочитанные
байты. Второй - битый хвост: обход отдаёт то, что успел найти, а не падает.
"""

from __future__ import annotations

from tests.domain.frames.mkv.blocks import elem, ident, length
from torrcast.domain.frames.mkv.ids import CUE_POINT, CUE_TIME, SEGMENT
from torrcast.domain.frames.mkv.walk import walk


def test_the_children_come_back_with_identifier_size_and_offset() -> None:
    """Соседи по куску читаются подряд, каждый со своим размером и смещением тела."""
    buf = elem(CUE_TIME, b"\x01\x02") + elem(CUE_POINT, b"\x03")
    found = walk(buf, 0, len(buf))

    assert [(kind, size) for kind, size, _data in found] == [(CUE_TIME, 2), (CUE_POINT, 1)]
    assert buf[found[0][2] : found[0][2] + 2] == b"\x01\x02"


def test_an_element_longer_than_the_buffer_stops_the_walk() -> None:
    """Segment не влез в голову: он сам найден, а соседа за ним искать негде."""
    buf = ident(SEGMENT) + length(1 << 40) + elem(CUE_TIME, b"\x01")
    found = walk(buf, 0, len(buf))

    assert [kind for kind, _size, _data in found] == [SEGMENT]


def test_a_broken_tail_returns_what_was_found() -> None:
    """Хвост не разобрался - отдаём найденное: карта из части куска лучше отказа."""
    buf = elem(CUE_TIME, b"\x01") + b"\x00\x00"
    found = walk(buf, 0, len(buf))

    assert [kind for kind, _size, _data in found] == [CUE_TIME]
