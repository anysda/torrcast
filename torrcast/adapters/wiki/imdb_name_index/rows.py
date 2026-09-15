"""Чтение одного имени из дискового индекса IMDb."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from torrcast.domain.slugify import slugify


def rows(target: Path, title: str) -> list[tuple[str, str, str, str, str]] | None:
    """Вернуть строки одного имени или ``None``, если готового индекса нет."""
    try:
        with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
            return list(
                connection.execute(
                    "SELECT tconst, kind, original, year, name FROM picture WHERE name_key = ?",
                    (slugify(title),),
                )
            )
    except sqlite3.Error:
        return None


__all__ = ["rows"]
