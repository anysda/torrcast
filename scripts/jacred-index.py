#!/usr/bin/env python3
"""Build a compact, local SQLite FTS catalogue from JacRed FileDB.

FileDB records are gzip-compressed JSON objects.  This reader is original MIT code;
it does not link, copy, or run JacRed's AGPL application.
"""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

SCHEMA = """
CREATE TABLE release(id INTEGER PRIMARY KEY, title TEXT NOT NULL, magnet TEXT NOT NULL,
 size INTEGER NOT NULL, seeders INTEGER NOT NULL, leechers INTEGER NOT NULL, created TEXT NOT NULL);
CREATE VIRTUAL TABLE search USING fts5(
 title, content='release', content_rowid='id', tokenize='unicode61');
CREATE TRIGGER release_ai AFTER INSERT ON release BEGIN
 INSERT INTO search(rowid,title) VALUES(new.id,new.title); END;
"""


def records(root: Path) -> Iterator[tuple[str, str, int, int, int, str]]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as source:
                raw = json.load(source)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        for item in raw.values():
            if not isinstance(item, dict):
                continue
            title, magnet = item.get("title"), item.get("magnet")
            if not isinstance(title, str) or not isinstance(magnet, str) or not magnet:
                continue
            yield (
                title,
                magnet,
                int(item.get("size") or 0),
                int(item.get("sid") or 0),
                int(item.get("pir") or 0),
                str(item.get("createTime") or ""),
            )


def build(
    source: Path, target: Path, wait_for_idle: Callable[[], None] | None = None
) -> tuple[int, float]:
    """Write a complete new index then atomically publish it."""
    began = time.monotonic()
    fresh = target.with_suffix(".new")
    fresh.unlink(missing_ok=True)
    db = sqlite3.connect(fresh)
    db.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; " + SCHEMA)
    count = 0
    batch: list[tuple[str, str, int, int, int, str]] = []
    for row in records(source):
        if wait_for_idle:
            wait_for_idle()
        batch.append(row)
        if len(batch) == 1000:
            db.executemany(
                "INSERT INTO release(title,magnet,size,seeders,leechers,created) "
                "VALUES(?,?,?,?,?,?)",
                batch,
            )
            db.commit()
            count += len(batch)
            batch.clear()
    if batch:
        db.executemany(
            "INSERT INTO release(title,magnet,size,seeders,leechers,created) VALUES(?,?,?,?,?,?)",
            batch,
        )
        count += len(batch)
    if not count:
        db.close()
        fresh.unlink(missing_ok=True)
        raise ValueError("FileDB contains no usable releases")
    if wait_for_idle:
        wait_for_idle()
    db.execute("INSERT INTO search(search) VALUES('optimize')")
    db.commit()
    db.close()
    os.replace(fresh, target)
    return count, time.monotonic() - began


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: jacred-index.py FILEDB_DIR INDEX.sqlite")
    rows, elapsed = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"indexed {rows} releases in {elapsed:.1f} s")
