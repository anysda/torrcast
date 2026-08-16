"""Правило word list; используют модели и фасады разбора имён."""

from __future__ import annotations


def _word_list(slug: str) -> list[str]:
    return [word for word in slug.split("-") if len(word) > 1]


__all__ = ["_word_list"]
