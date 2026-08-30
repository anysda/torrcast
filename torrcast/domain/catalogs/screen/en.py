"""Английские надписи кластера строки показа."""

from __future__ import annotations


def en() -> dict[str, str]:
    """Вернуть английский каталог кластера строки показа."""
    return {
        "screen.line": "{tag} screen: {pos} of {dur} · {state}",
    }
