"""Число разобранного JSON: то же, что `float`, только с названным входом."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_value import JsonValue


def json_number(value: JsonValue) -> float:
    """Число из разобранного JSON. Не число - ``TypeError``, ровно как у :func:`float`.

    Молча подставлять ноль нельзя: ноль в выжимке следа читается как измеренная величина,
    и подмена сломанного поля нулём соврала бы про показ. Поэтому правило тут ровно то же,
    что было у голого ``float(...)``: строка и число читаются, остальное - ошибка.
    """
    if isinstance(value, str | int | float):
        return float(value)
    raise TypeError(phrase("trace.not_a_number", kind=type(value).__name__))
