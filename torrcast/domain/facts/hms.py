"""Минуты в человеческую строку хронометража; зовёт сборка справки."""

from __future__ import annotations

from torrcast.domain.facts.settings import RUNTIME_CAP_MINUTES


def hms(minutes: int) -> str:
    """Минуты → «1 ч 47 мин»; ровный час — «1 ч»; меньше часа — «47 мин»; ноль — пусто.

    Неправдоподобная длина — тоже пусто (:data:`RUNTIME_CAP_MINUTES`). Строка эта не
    украшение: по хронометражу человек отличает нужную картину от однофамильца, и
    выдуманное число хуже отсутствующего.
    """
    if minutes <= 0 or minutes > RUNTIME_CAP_MINUTES:
        return ""
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest} мин"
    return f"{hours} ч {rest} мин" if rest else f"{hours} ч"
