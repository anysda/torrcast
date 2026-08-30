"""EBML-число переменной длины: с него начинается любой элемент матрёшки."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase


def vint(buf: bytes, i: int, keep_marker: bool) -> tuple[int, int]:
    """EBML-число переменной длины: идентификатор читается с маркером, размер — без."""
    head = buf[i]
    if head == 0:
        raise ValueError(phrase("frames.ebml_broken"))
    width, mask = 1, 0x80
    while not head & mask:
        mask >>= 1
        width += 1
    raw = buf[i : i + width]
    if keep_marker:
        return int.from_bytes(raw, "big"), i + width
    value = head & (mask - 1)
    for byte in raw[1:]:
        value = value << 8 | byte
    return value, i + width
