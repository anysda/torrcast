"""Русские надписи кластера главного файла настроек."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера главного файла настроек."""
    return {
        "main_config.unreadable": "битый конфиг {path}: {reason}",
        "main_config.not_an_object": "битый конфиг {path}: ожидался объект JSON",
        "main_config.write_failed": "не смог записать {path}: {reason}",
    }
