#!/usr/bin/env python3
"""Local read-only search adapter for AniLibria's public API."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ORIGINS = ("https://anilibria.top", "https://api.anilibria.app")
TIMEOUT = 3.0
LIMIT = 5


def _words(value: str) -> set[str]:
    """Words suitable for checking whether the catalog result answers the query."""
    return set(re.findall(r"[\w]+", value.casefold()))


def _matches(release: dict[str, Any], query: str) -> bool:
    """Reject fuzzy API hits that do not contain the requested title."""
    wanted = _words(query)
    if not wanted:
        return False
    name = release.get("name")
    names = name.values() if isinstance(name, dict) else (name,)
    names = (*names, release.get("alias"))
    return any(wanted <= _words(value) for value in names if isinstance(value, str))


def _json(origin: str, path: str) -> Any:
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
    """Return torrents; one dead origin or release narrows results instead of failing."""
    releases: list[dict[str, Any]] = []
    origin = ""
    path = "/api/v1/app/search/releases?" + urllib.parse.urlencode({"query": query})
    for candidate in ORIGINS:
        try:
            answer = _json(candidate, path)
            if isinstance(answer, list):
                releases = [row for row in answer if isinstance(row, dict) and _matches(row, query)]
                releases, origin = releases[:LIMIT], candidate
                break
        # SubprocessError belongs here as much as OSError: a hung origin leaves
        # `subprocess.run` in its own TimeoutExpired, which is NOT an OSError. Uncaught it
        # would leave the handler through a dropped connection, and Prowlarr answers a
        # dropped connection with a ban ladder - and the step for a source that does not
        # answer is a whole day, so one stall would cost far more than this source is worth.
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
    if not origin:
        return []

    def torrents(release: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            details = _json(origin, f"/api/v1/anime/torrents/release/{int(release['id'])}")
        # The same TimeoutExpired reaches this call too, and here a stall is likelier: the
        # details of one release are asked for after the listing already answered.
        except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
            return []
        found = details.get("torrents", details) if isinstance(details, dict) else details
        return found if isinstance(found, list) else []

    # Two requests at once is within the source's measured safe window and bounds latency.
    with ThreadPoolExecutor(max_workers=2) as pool:
        groups = pool.map(torrents, releases)
    rows: list[dict[str, Any]] = []
    for group in groups:
        for torrent in group:
            if not isinstance(torrent, dict) or not torrent.get("magnet"):
                continue
            rows.append(
                {
                    "title": torrent.get("label") or torrent.get("filename") or query,
                    "magnet": torrent["magnet"],
                    "size": torrent.get("size") or 0,
                    "seeders": torrent.get("seeders") or 0,
                    "leechers": torrent.get("leechers") or 0,
                    "date": torrent.get("created_at") or "1970-01-01T00:00:00+00:00",
                }
            )
    return rows


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/ping":
            body = b'{"status":"ok"}'
        elif parsed.path == "/search":
            query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
            # Prowlarr tests an indexer without keywords before saving it.
            body = json.dumps({"results": search(query or "Kaiba")}, ensure_ascii=False).encode()
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
        ("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 9697), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
