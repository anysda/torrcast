"""Находит профиль телевизора по ключу настройки."""

from torrcast.domain.profile import PROFILES, Profile

__all__ = ["by_key"]


def by_key(key: str) -> Profile | None:
    """Вернуть профиль по ключу либо ``None`` для неизвестного ключа."""
    return PROFILES.get(key.strip().lower())
