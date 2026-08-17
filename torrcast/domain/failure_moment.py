"""Отметка отказа индексера глазами Prowlarr, переведённая в секунды эпохи."""

from __future__ import annotations

import re
from datetime import datetime


def failure_moment(failed: str) -> float | None:
    """Отметка последнего отказа в секундах эпохи; ``None`` - не прочли.

    ``failed`` - UTC-время вида «2026-08-09T20:13:28Z». Дробную часть секунды отрезаем:
    Prowlarr отдаёт её то в шесть знаков, то в семь, а :meth:`~datetime.datetime.fromisoformat`
    до 3.12 семь не принимает.
    """
    try:
        return datetime.fromisoformat(
            re.sub(r"\.\d+", "", failed).replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None


__all__ = ["failure_moment"]
