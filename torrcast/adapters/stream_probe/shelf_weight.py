"""Сколько на полке записей и сколько они весят байт.

Нужно это одному ``cast doctor``: кэши тихо растут годами."""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def shelf_weight(directory: Path) -> tuple[int, int]:
    """Сколько на полке записей и сколько они весят байт; нет полки - ``(0, 0)``.

    Нужно одному ``cast doctor``: кэши тихо растут годами, и цифра рядом с потолком -
    единственный способ заметить это раньше, чем кончится место.
    """
    count = 0
    weight = 0
    with contextlib.suppress(OSError), os.scandir(directory) as reading:
        for entry in reading:
            if not entry.name.endswith(".json"):
                continue
            count += 1
            with contextlib.suppress(OSError):
                weight += entry.stat().st_size
    return count, weight
