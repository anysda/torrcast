"""Сохранённое тело полок, которое фон пересобирает холодным заходом (:mod:`web.shelf_pass`).

Холодное - собранное не этим правилом (:mod:`web.built_by_rule`) или без одной из полок:
тело прошлой сборки с пустой «Популярное» иначе стояло бы на главной пустым рядом до
медленного захода, и страница, увидев его без метки сборки, не спрашивала бы полки снова.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import built_by_rule

#: Порядок полок: первой руки берут «Новинки», как и прежде шла сборка.
SHELVES: Final = ("fresh", "popular")


def cold(body: dict[str, JsonValue]) -> bool:
    """Тело не собрано этим правилом или в нём нет полки."""
    whole = all(body.get(shelf) for shelf in SHELVES)
    return not (body.get("built_at") and built_by_rule(body) and whole)


__all__ = ["SHELVES", "cold"]
