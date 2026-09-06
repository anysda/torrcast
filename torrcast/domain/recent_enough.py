"""Правило recent enough; используют модели и фасады разбора имён."""

from __future__ import annotations

from datetime import datetime, timedelta


def recent_enough(published: datetime, now: datetime, days: int) -> bool:
    """Раздача внутри окна ленты: не старше ``days`` суток до ``now``.

    Верхнюю границу нарочно не проверяем: часы Prowlarr не наши, и раздача, отметка
    которой на секунду обогнала наши часы, всё равно самая свежая находка ленты, а не
    повод её выбросить.
    """
    return published >= now - timedelta(days=days)


__all__ = ["recent_enough"]
