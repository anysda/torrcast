"""Правило same words; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain.paired import _paired


def same_words(want: str, base: str) -> bool:
    return _paired(want.split("-"), base.split("-"))


__all__ = ["same_words"]
