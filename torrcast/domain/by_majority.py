"""Правило by majority; используют модели и фасады разбора имён."""

from __future__ import annotations

from collections import Counter


def by_majority(counted: Counter[str]) -> str:
    return min(counted, key=lambda name: (-counted[name], len(name), name))


__all__ = ["by_majority"]
