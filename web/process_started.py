"""Миг старта процесса на часах ``time.monotonic``: от него меряется холодная полка.

Полку меряют от старта службы, а фон полок встаёт лишь после подъёма (2.4-6.6 с на
стенде): срок, отсчитанный от фона, уезжал за цель на время подъёма. Linux называет
старт процесса в ``/proc/self/stat`` (тики от загрузки, те же часы, что ``CLOCK_BOOTTIME``).
Где этого нет, старт процесса - миг вопроса: прежний отсчёт от фона.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

_STAT = Path("/proc/self/stat")
#: Поле ``starttime`` после имени процесса в скобках (поле 22 в ``proc(5)``).
_STARTTIME = 19


def process_started() -> float:
    """Когда стартовал этот процесс, по ``time.monotonic``; не узнать - сейчас."""
    now = time.monotonic()
    try:
        ticks = int(_STAT.read_text().rsplit(")", 1)[1].split()[_STARTTIME])
        age = time.clock_gettime(time.CLOCK_BOOTTIME) - ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, AttributeError):
        return now
    return now - max(0.0, age)


__all__ = ["process_started"]
