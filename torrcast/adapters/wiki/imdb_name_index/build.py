"""Сборка дискового индекса русских прокатных имён IMDb."""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from torrcast.domain.facts.imdb_rows import _repair_ru_name
from torrcast.domain.slugify import slugify


def build(names_path: Path, target: Path | None = None) -> bool:
    """Собрать индекс, только если выгрузка изменилась; вернуть, была ли запись."""
    target = _index_path(names_path) if target is None else target
    try:
        stamp = names_path.stat()
    except OSError:
        return False
    if _current(target, stamp):
        return False
    temporary = target.with_name(f"{target.name}.part")
    try:
        temporary.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(
                """
                CREATE TABLE picture (
                    name_key TEXT NOT NULL,
                    tconst TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    original TEXT NOT NULL,
                    year TEXT NOT NULL,
                    name TEXT NOT NULL,
                    PRIMARY KEY (name_key, tconst)
                ) WITHOUT ROWID;
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
                """
            )
            with names_path.open(encoding="utf-8") as source:
                connection.executemany(
                    "INSERT OR IGNORE INTO picture VALUES (?, ?, ?, ?, ?, ?)", _rows(source)
                )
            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (("mtime_ns", str(stamp.st_mtime_ns)), ("size", str(stamp.st_size))),
            )
            connection.commit()
        finally:
            connection.close()
        os.replace(temporary, target)
    except (OSError, sqlite3.Error):
        temporary.unlink(missing_ok=True)
        return False
    return True


def _index_path(names_path: Path) -> Path:
    return names_path.with_suffix(".sqlite3")


def _current(target: Path, stamp: os.stat_result) -> bool:
    try:
        with sqlite3.connect(f"file:{target}?mode=ro", uri=True) as connection:
            values = dict(connection.execute("SELECT key, value FROM metadata"))
    except sqlite3.Error:
        return False
    return values == {"mtime_ns": str(stamp.st_mtime_ns), "size": str(stamp.st_size)}


def _rows(source: Iterable[str]) -> Iterator[tuple[str, str, str, str, str, str]]:
    for line in source:
        fields = line.rstrip("\n").split("\t")
        name, tconst, kind, original, year = [*fields, "", "", "", "", ""][:5]
        if name and tconst:
            name = _repair_ru_name(name)
            yield (slugify(name), tconst, kind, original, year, name)


def _main() -> int:
    if len(sys.argv) not in (2, 3):
        return 2
    names = Path(sys.argv[1])
    target = Path(sys.argv[2]) if len(sys.argv) == 3 else _index_path(names)
    build(names, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["build"]
