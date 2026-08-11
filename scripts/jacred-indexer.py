#!/usr/bin/env python3
"""Read-only Cardigann adapter for JacRed's public torrent search API."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# One origin, and that is measured, not overlooked: the catalog's other public names are
# not a second edge. One family serves an incomplete certificate chain and then tears the
# body mid-answer, another never answers, the rest no longer resolve. So the second way in
# is a second ROUTE to this same address rather than a second name - the shim row in
# install.sh carries it, because without a name in the handshake the address returns the
# very same answer.
ORIGINS = ("https://api.jacred.su",)
TIMEOUT = 3.0
LIMIT = 100


def _json(origin: str, query: str) -> Any:
    path = "/api/search?" + urllib.parse.urlencode({"query": query, "sort": "sid", "limit": LIMIT})
    done = subprocess.run(
        ["curl", "-4fsS", "-m", str(TIMEOUT), "-A", "torrcast/1", origin + path],
        capture_output=True,
        check=False,
        timeout=TIMEOUT + 1,
    )
    if done.returncode:
        raise OSError(done.stderr.decode(errors="replace"))
    return json.loads(done.stdout)


def search(query: str) -> list[dict[str, Any]]:
    """Return usable magnets; an absent API is an empty optional source."""
    if not query.strip():
        return []
    for origin in ORIGINS:
        try:
            answer = _json(origin, query)
        # SubprocessError belongs here as much as OSError: a hung upstream leaves
        # `subprocess.run` in its own TimeoutExpired, which is NOT an OSError. Uncaught it
        # would leave the handler through a dropped connection, and Prowlarr answers a
        # dropped connection with a ban ladder - a stall of the source would cost the
        # catalog far more than the source itself is worth.
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        found = answer.get("results") if isinstance(answer, dict) else None
        if not isinstance(found, list):
            continue
        rows: list[dict[str, Any]] = []
        for item in found:
            if not isinstance(item, dict) or not item.get("title") or not item.get("magnet"):
                continue
            rows.append(
                {
                    "title": item["title"],
                    "magnet": item["magnet"],
                    "size": item.get("size") or 0,
                    "seeders": item.get("seeders") or 0,
                    "leechers": item.get("peers") or 0,
                    "date": item.get("created_at") or "1970-01-01",
                }
            )
        return rows
    return []


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/ping":
            body = b'{"status":"ok"}'
        elif parsed.path == "/search":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
            body = json.dumps({"results": search(query or "матрица")}, ensure_ascii=False).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    ThreadingHTTPServer(
        ("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 9698), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
