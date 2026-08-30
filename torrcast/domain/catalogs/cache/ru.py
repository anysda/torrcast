"""Русские надписи кластера запаса показа в кэше службы раздач."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера запаса показа в кэше службы раздач."""
    return {
        "cache.by_measurement": "по замеру",
        "cache.by_estimate": "по оценке",
        "cache.reserve_unknown_no_answer": (
            "запас в кэше службы неизвестен - служба раздач не отвечает"
        ),
        "cache.reserve_unknown_silent": "запас в кэше службы неизвестен - служба про него молчит",
        "cache.reserve_empty": "кэш службы пуст, запаса показа в нём нет",
        "cache.reserve_unconvertible": (
            "запас в кэше службы есть, в минуты не перевести - битрейт файла неизвестен"
        ),
        "cache.reserve_under_minute": "в кэше службы запас меньше минуты показа",
        "cache.reserve_minutes": "в кэше службы запас ещё на {minutes} мин показа ({source})",
    }
