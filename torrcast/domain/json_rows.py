"""Список разобранного JSON: что угодно - в список, чужое - в пустой."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue


def json_rows(value: JsonValue) -> list[JsonValue]:
    """Массив JSON как список; ``None`` и не-массив читаются как пустой список.

    Тот же смысл, что у ``payload.get("pages", []) or []``: поля нет, поле пустое и поле
    другого вида - для читателя это одинаковое «перебирать нечего».
    """
    return value if isinstance(value, list) else []
