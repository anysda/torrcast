"""Правило words; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.word_list import _word_list


def _words(slug: str) -> set[str]:
    return set(_word_list(slug))


__all__ = ["_words"]
