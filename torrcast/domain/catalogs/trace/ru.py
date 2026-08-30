"""Русские надписи кластера ленты меток."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера ленты меток.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "trace.no_marks": "меток нет",
        "trace.column_phase": "фаза",
        "trace.column_from_zero": "от нуля",
        "trace.column_cost": "цена",
        "trace.not_a_number": "в JSON ожидалось число, а лежит {kind}",
    }
