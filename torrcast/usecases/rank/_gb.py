"""Размер раздачи словами; зовут таблица релизов и строка запуска."""

from __future__ import annotations


def _gb(size: int) -> str:
    return f"{size / 1024**3:.1f} ГБ" if size else "-"
