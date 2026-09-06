"""Имя с подзаголовком узнаётся и без номера перед двоеточием."""

from __future__ import annotations

import re

_NUMBER_RE = re.compile(r"(?i)\s+(?:[1-9]\d?|[ivx]{1,4})$")


def numbered_subtitle(name: str) -> str:
    """Снять номер только перед подзаголовком, сохранив сам подзаголовок целиком.

    «Пираты 3: На краю света» и «Пираты: На краю света» называют одну работу.
    Голое «Пираты 3» ничего не доказывает: без общего оригинала или явно названного
    псевдонима узнать подзаголовок нельзя. Номер ВНУТРИ подзаголовка остаётся:
    «Сойка-пересмешница. Часть 1» и «Часть 2» - разные фильмы.
    """
    head, colon, tail = name.partition(":")
    if not colon or not tail.strip():
        return name
    head = _NUMBER_RE.sub("", head.strip())
    return f"{head}: {tail.strip()}"


__all__ = ["numbered_subtitle"]
