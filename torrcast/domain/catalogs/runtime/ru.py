"""Русские надписи кластера композиционного корня."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера композиционного корня."""
    return {
        "runtime.announced_language": "язык: {name}",
        "runtime.config_unread": "конфиг не прочитан",
        "runtime.receiver_passport": "паспорт приёмника",
    }
