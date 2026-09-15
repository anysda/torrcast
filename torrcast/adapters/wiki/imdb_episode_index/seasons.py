"""Сезоны одного сериала из дискового индекса серий IMDb (:mod:`.build`)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def seasons(target: Path, tconst: str) -> dict[int, tuple[int, ...]] | None:
    """Номера серий по сезонам; ``None`` - индекса нет, пустой ответ - сериала в нём нет."""
    if not tconst.startswith("tt") or not tconst[2:].isdigit():
        return {}
    try:
        with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
            found = list(
                connection.execute(
                    "SELECT season, numbers FROM season WHERE parent = ? ORDER BY season",
                    (int(tconst[2:]),),
                )
            )
    except sqlite3.Error:
        return None
    return {season: _numbers(numbers) for season, numbers in found}


def _numbers(spans: str) -> tuple[int, ...]:
    out: list[int] = []
    for span in spans.split(","):
        low, _, high = span.partition("-")
        out.extend(range(int(low), int(high or low) + 1))
    return tuple(out)


__all__ = ["seasons"]
