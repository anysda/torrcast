"""Очередь приговоров одной полки."""

from __future__ import annotations

from torrcast.domain.json_value import JsonValue

__all__ = ["shelf_lane"]


def shelf_lane(records: list[JsonValue]) -> list[tuple[str, str]]:
    """Очередь приговоров полки: (запрос, ключ) записей с обложкой, в порядке полки.

    Порядок тот же, что у отбора :func:`web.shelf_tiles._covered`.
    """
    return [
        (str(record.get("query", "")), str(record.get("key", "")))
        for record in records
        if isinstance(record, dict) and record.get("poster")
    ]
