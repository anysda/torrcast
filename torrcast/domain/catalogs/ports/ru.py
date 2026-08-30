"""Русские надписи кластера портовых слотов."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера портовых слотов."""
    return {
        "ports.show_unit_not_installed": "юнит показа не назначен: приложение не собрано",
        "ports.state_store_not_installed": (
            "хранилище состояния не назначено: приложение не собрано"
        ),
    }
