"""Зеркало :mod:`torrcast.domain.frames.mkv.ids`: идентификаторы EBML и размеры кусков.

Мера тут одна и злая: идентификатор обязан лежать ВМЕСТЕ со своим маркером длины, ровно
как в файле. Потеряй он маркер - обход матрёшки сравнивал бы числа с разной шириной и не
узнавал бы ни одного элемента.
"""

from __future__ import annotations

from torrcast.domain.frames.mkv import ids


def test_the_identifiers_keep_their_length_marker() -> None:
    """Старший бит первого байта - маркер ширины, и он на месте у всех четырёх ширин."""
    for value, width in ((ids.SEGMENT, 4), (ids.INFO, 4), (ids.SEEK, 2), (ids.CUE_POINT, 1)):
        raw = value.to_bytes(width, "big")
        assert raw[0] & (0x80 >> (width - 1)), f"{value:#x} потерял маркер длины"


def test_the_chunk_sizes_are_the_measured_ones() -> None:
    """Куски головы и Cues - замеренные величины, а не круглые числа наугад."""
    assert ids.HEAD_BYTES == 4 << 20
    assert ids.CUES_CHUNK == 1 << 20
