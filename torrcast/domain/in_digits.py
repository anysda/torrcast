"""Правило in digits; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data import _NUMERALS


def in_digits(slug: str) -> str:
    return "-".join(_NUMERALS.get(word, word) for word in slug.split("-"))


__all__ = ["in_digits"]
