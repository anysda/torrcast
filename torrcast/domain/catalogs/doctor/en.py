"""Английские надписи кластера самопроверки."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера самопроверки."""
    return {
        "doctor.all_clear": "all clear",
        "doctor.problems": "problems: {bad} - see the “bad” lines above",
    }
