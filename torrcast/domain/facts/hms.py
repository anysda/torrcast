"""Минуты в человеческую строку хронометража; зовёт сборка справки."""

from __future__ import annotations


def hms(minutes: int) -> str:
    """Минуты → «1 ч 47 мин»; ровный час — «1 ч»; меньше часа — «47 мин»; ноль — пусто."""
    if minutes <= 0:
        return ""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} мин"
    return f"{hours} ч {rest} мин" if rest else f"{hours} ч"
