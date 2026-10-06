"""Отметка тела полок: сколько плиток в хвосте полки перенесено с прежнего правила.

Перенос описан в :mod:`web._stale_tiles`; отметку читает порог усыхания
(:func:`web.held_by.held_by`), чтобы мерить полку только своими плитками.
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue

#: Поле тела полок: сколько плиток в хвосте каждой полки перенесено с прежнего правила.
CARRIED: Final = "carried"


def carried(body: dict[str, JsonValue], shelf: str) -> int:
    """Сколько плиток полки перенесено с прежнего правила; нет отметки - ни одной."""
    marks = body.get(CARRIED)
    count = marks.get(shelf) if isinstance(marks, dict) else None
    return count if isinstance(count, int) else 0


__all__ = ["CARRIED", "carried"]
