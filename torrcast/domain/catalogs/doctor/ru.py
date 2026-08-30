"""Русские надписи кластера самопроверки."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера самопроверки."""
    return {
        "doctor.all_clear": "всё в порядке",
        "doctor.problems": "проблем: {bad} - смотри строки «плохо» выше",
    }
