"""Зеркало :mod:`torrcast.domain.frames.mkv.vint`: число переменной длины EBML.

Мера про развилку ``keep_marker``: идентификатор элемента сравнивают с маркером ширины
(так он лежит в файле), а размер тела - без него. Спутай их - обход шагнул бы мимо.
"""

from __future__ import annotations

import pytest

from torrcast.domain.frames.mkv.vint import vint


def test_the_identifier_keeps_the_marker_and_the_size_drops_it() -> None:
    """Одни и те же байты: с маркером - 0x4DBB, без маркера - 0x0DBB."""
    buf = b"\x4d\xbb"
    assert vint(buf, 0, keep_marker=True) == (0x4DBB, 2)
    assert vint(buf, 0, keep_marker=False) == (0x0DBB, 2)


def test_a_single_byte_number_ends_right_after_itself() -> None:
    """Однобайтовое число: маркер в старшем бите, значение - остаток."""
    assert vint(b"\x81\xff", 0, keep_marker=False) == (1, 1)


def test_a_zero_byte_is_not_a_number() -> None:
    """Нулевой байт ширины не задаёт: разбор обязан сказать это, а не зациклиться."""
    with pytest.raises(ValueError, match="a broken EBML number"):
        vint(b"\x00\x00", 0, keep_marker=False)
