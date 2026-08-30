"""Русские надписи кластера строки показа."""

from __future__ import annotations


def ru() -> dict[str, str]:
    """Вернуть русский каталог кластера строки показа."""
    return {
        "screen.line": "{tag} экран: {pos} из {dur} · {state}",
    }
