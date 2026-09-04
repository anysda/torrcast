#!/usr/bin/env python3
"""Read-only Cardigann adapter for JacRed's public torrent search API."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from collections.abc import Callable
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


#: How the API is asked: the live `_json` in production, a stand-in under test.
Fetch = Callable[[str, str], Any]


def search(query: str, fetch: Fetch = _json) -> list[dict[str, Any]]:
    """Return usable magnets; an absent API is an empty optional source.

    `fetch` carries its production default, so the handler calls this with one argument
    and the behaviour is unchanged; a stand can hand in answers without a network.
    """
    if not query.strip():
        return []
    for origin in ORIGINS:
        try:
            answer = fetch(origin, query)
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


#: Which loopback address to listen on.  It is the one macOS keeps on lo0 by default, and
#: the neighbour explains next door why nothing else out of 127/8 will do
#: (:mod:`scripts.anilibria-indexer`).  Prowlarr tells the two of us apart by the host
#: string it was given, not by the address, so sharing this one costs us nothing.
HOST = "127.0.0.1"


def main() -> None:
    ThreadingHTTPServer(
        (HOST, int(sys.argv[1]) if len(sys.argv) > 1 else 9698), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
