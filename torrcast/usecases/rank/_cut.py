"""Обрезка длинной ячейки таблицы; зовут таблица релизов и команда озвучек."""

from __future__ import annotations


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."
