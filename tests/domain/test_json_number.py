"""Зеркало :mod:`torrcast.domain.json_number`: число читается числом, а не число - ошибкой."""

from __future__ import annotations

import pytest

from torrcast.domain.json_number import json_number


def test_numbers_and_numeric_strings_read_the_same_way_float_read_them() -> None:
    """Целое, дробное, булево и числовая строка - ровно то же, что отдавал ``float``."""
    assert json_number(3) == 3.0
    assert json_number(1.5) == 1.5
    assert json_number(True) == 1.0
    assert json_number("2.5") == 2.5


def test_a_broken_field_raises_instead_of_quietly_becoming_zero() -> None:
    """Ноль вместо сломанного поля соврал бы про показ: ноль тут - измеренная величина.

    Поэтому правило то же, что было у голого ``float(...)``: не число - ``TypeError``.
    """
    with pytest.raises(TypeError):
        json_number(None)
    with pytest.raises(TypeError):
        json_number({"pos": 1})
    with pytest.raises(TypeError):
        json_number([1])
