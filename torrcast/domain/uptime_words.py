"""Секунды непрерывной работы человеческими словами; зовут их строки самопроверки."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase

#: Секунд в часе и в сутках - крупнее суток в строке не нужно: разбор смерти показа
#: спрашивает «перезагружался ли», а не календарь.
_HOUR = 3600
_DAY = 24 * _HOUR


def uptime_words(seconds: float) -> str:
    """Сколько прибор на ногах - словами, с точностью до следующей единицы вниз.

    Минуты рядом с сутками не значат ничего, поэтому крупная единица отсекает мелкую:
    сутки называют часы, часы - минуты, а меньше часа считается минутами.
    """
    total = max(0, int(seconds))
    if total >= _DAY:
        return phrase("spans.days_hours", days=total // _DAY, hours=total % _DAY // _HOUR)
    if total >= _HOUR:
        return phrase("spans.hours_minutes", hours=total // _HOUR, minutes=total % _HOUR // 60)
    return phrase("spans.minutes", minutes=total // 60)
