#!/usr/bin/env python3
"""Read-only local Torznab adapter over the JacRed FileDB-derived SQLite index."""

from __future__ import annotations

import calendar
import datetime
import json
import re
import sqlite3
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import zip_longest
from pathlib import Path
from typing import Any

INDEX = Path("/var/lib/torrcast/jacred/index.sqlite")
LIMIT = 100
WORDS = re.compile(r"[\w]+", re.UNICODE)
HOST = "127.0.0.1"
JOINT = " | "


def _match(query: str) -> str:
    return " AND ".join(f'"{word.replace(chr(34), "")}"*' for word in WORDS.findall(query))


def _unix(value: str) -> str:
    try:
        return str(calendar.timegm(datetime.datetime.fromisoformat(value).timetuple()))
    except (TypeError, ValueError):
        return "0"


def _rows(db: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    match = _match(query)
    if not match:
        return []
    rows = db.execute(
        "SELECT release.title,magnet,size,seeders,leechers,created FROM search "
        "JOIN release ON release.id=search.rowid WHERE search MATCH ? "
        "ORDER BY seeders DESC LIMIT ?",
        (match, LIMIT),
    )
    return [
        {
            "title": title,
            "magnet": magnet,
            "size": size,
            "seeders": seeders,
            "leechers": leechers,
            "date": _unix(created),
        }
        for title, magnet, size, seeders, leechers, created in rows
    ]


def search(query: str, index: Path = INDEX) -> list[dict[str, Any]]:
    """Search only the local index; a missing or partial index is an empty source."""
    texts = [text.strip() for text in query.split(JOINT) if text.strip()]
    if not texts or not index.is_file():
        return []
    try:
        with sqlite3.connect(f"file:{index}?mode=ro", uri=True) as db:
            answers = [_rows(db, text) for text in texts]
    except sqlite3.Error:
        return []
    found: dict[str, dict[str, Any]] = {}
    for row in (row for tier in zip_longest(*answers) for row in tier if row is not None):
        found.setdefault(str(row["magnet"]), row)
    return list(found.values())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/ping":
            body = b'{"status":"ok"}'
        elif parsed.path == "/search":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0]
            body = json.dumps({"results": search(query)}, ensure_ascii=False).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer(
        (HOST, int(sys.argv[1]) if len(sys.argv) > 1 else 9698), Handler
    ).serve_forever()
