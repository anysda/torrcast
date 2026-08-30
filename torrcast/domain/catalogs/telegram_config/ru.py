"""Русские надписи кластера настройки Telegram-бота."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера настройки Telegram-бота."""
    return {
        "telegram_config.broken_file": "битая настройка {path}: ожидался объект JSON",
    }
