"""Правило normalize quality; используют модели и фасады разбора имён."""

from __future__ import annotations


def _normalize_quality(value: str) -> str:
    lowered = value.lower()
    return "2160p" if lowered in {"4k", "uhd"} else lowered


__all__ = ["_normalize_quality"]
