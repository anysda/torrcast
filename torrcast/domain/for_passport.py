"""Выбирает измеренный профиль по паспорту телевизора-приёмника."""

from typing import Final

from torrcast.domain.profile import ANDROID_TV, CAUTIOUS, Profile

__all__ = ["for_passport"]

_KNOWN: Final[tuple[tuple[str, Profile], ...]] = (
    ("xiaomi", ANDROID_TV),
    ("android tv", ANDROID_TV),
    ("androidtv", ANDROID_TV),
)


def for_passport(maker: str = "", model: str = "", name: str = "") -> Profile:
    """Выбрать профиль по трём полям паспорта; неизвестному дать осторожный."""
    haystack = " ".join(part.lower() for part in (maker, model, name) if part)
    for word, profile in _KNOWN:
        if word in haystack:
            return profile
    return CAUTIOUS
