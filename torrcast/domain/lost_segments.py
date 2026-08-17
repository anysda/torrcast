"""Разрывы в журнале декодера: сколько кусков до него не доехало."""

from __future__ import annotations

import re
from typing import Final

#: Строки ffmpeg, означающие, что кусок не доехал: для приёмки это разрыв.
_LOST: Final = re.compile(r"Failed to open segment|Error opening|Cannot reload|skipping", re.I)


def lost_segments(journal: str) -> int:
    """Сколько раз декодер сказал, что куска нет."""
    return len(_LOST.findall(journal))
