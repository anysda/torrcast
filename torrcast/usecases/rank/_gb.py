"""Размер раздачи словами; зовут таблица релизов и строка запуска."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase


def _gb(size: int) -> str:
    return phrase("rank.size_gb", value=f"{size / 1024**3:.1f}") if size else "-"
