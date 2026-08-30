"""Русские надписи кластера промежутков времени."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера промежутков времени.

    Ключа, которого тут нет, продукт скажет по-английски
    (:func:`torrcast.domain.catalogs.phrase.phrase`): русский каталог - надстройка над
    английским, а не второй полный словарь, который обязан поспевать за первым.
    """
    return {
        "spans.days_hours": "{days} д {hours} ч",
        "spans.hours_minutes": "{hours} ч {minutes} мин",
        "spans.hours": "{hours} ч",
        "spans.minutes": "{minutes} мин",
    }
