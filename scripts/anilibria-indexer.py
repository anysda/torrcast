#!/usr/bin/env python3
"""Local read-only search adapter for AniLibria's public API."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ORIGINS = ("https://anilibria.top", "https://api.anilibria.app")
TIMEOUT = 3.0
LIMIT = 5
#: How long one release's torrent list may take, and how many times it may be asked.
#:
#: A healthy answer takes 0.25-0.40 s; what costs us is a rare upstream stall that runs
#: into the timeout. Measured on the live stand over eight rounds of five releases: the
#: old shape (two at a time, 3.0 s, no second try) spent 18.9 s and SILENTLY DROPPED six
#: releases out of forty, because a stalled detail call returns an empty list and the
#: release simply vanishes from the catalog. Asking with a short deadline and once more
#: on failure spent 8.6 s and dropped none. The second try is what keeps the catalog
#: whole; the short deadline is what makes the second try cheaper than the old first one.
DETAIL_TIMEOUT = 1.2
DETAIL_TRIES = 2


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


def _json(origin: str, path: str, seconds: float = TIMEOUT) -> Any:
    done = subprocess.run(
        ["curl", "-4fsS", "-m", str(seconds), "-A", "torrcast/1", origin + path],
        capture_output=True,
        check=False,
        timeout=seconds + 1,
    )
    if done.returncode:
        raise OSError(done.stderr.decode(errors="replace"))
    return json.loads(done.stdout)


#: How a page is fetched: the live `_json` in production, a stand-in under test.
#: The deadline is part of the seam because the listing and one release's details are
#: worth waiting for differently.
Fetch = Callable[..., Any]


def _listing(query: str, fetch: Fetch) -> tuple[list[dict[str, Any]], str]:
    """Both mirrors asked at once, and the answer taken in the order they are written down.

    That order is a PREFERENCE, not a queue. Asked one after the other, every search waited
    the first one out, and on the live stand the first one answers 403 to every query and
    costs 0.68 s before the second is even asked; on a query where the second one stalls the
    two costs added up to 3.69 s. Asked together, neither waits for the other, and WHICH
    catalogue we read does not move: the first mirror that answers a list still wins, no
    matter which came back sooner.
    """
    path = "/api/v1/app/search/releases?" + urllib.parse.urlencode({"query": query})
    pool = ThreadPoolExecutor(max_workers=len(ORIGINS), thread_name_prefix="anilibria-origin")
    asked = [(origin, pool.submit(fetch, origin, path)) for origin in ORIGINS]
    pool.shutdown(wait=False)
    for origin, answer in asked:
        try:
            rows = answer.result()
        # SubprocessError belongs here as much as OSError: a hung origin leaves
        # `subprocess.run` in its own TimeoutExpired, which is NOT an OSError. Uncaught it
        # would leave the handler through a dropped connection, and Prowlarr answers a
        # dropped connection with a ban ladder - and the step for a source that does not
        # answer is a whole day, so one stall would cost far more than this source is worth.
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if isinstance(rows, list):
            kept = [row for row in rows if isinstance(row, dict) and _matches(row, query)]
            return kept[:LIMIT], origin
    return [], ""


def search(query: str, fetch: Fetch = _json) -> list[dict[str, Any]]:
    """Return torrents; one dead origin or release narrows results instead of failing.

    `fetch` carries its production default, so the handler calls this with one argument
    and the behaviour is unchanged; a stand can hand in answers without a network.
    """
    releases, origin = _listing(query, fetch)
    if not origin:
        return []

    def torrents(release: dict[str, Any]) -> list[dict[str, Any]]:
        for _ in range(DETAIL_TRIES):
            try:
                details = fetch(
                    origin,
                    f"/api/v1/anime/torrents/release/{int(release['id'])}",
                    DETAIL_TIMEOUT,
                )
            # The same TimeoutExpired reaches this call too, and here a stall is likelier:
            # the details of one release are asked for after the listing already answered.
            # A stall is usually the source hiccupping rather than the release being gone,
            # so it is worth one more ask: giving up here quietly narrows the catalog.
            except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError):
                continue
            found = details.get("torrents", details) if isinstance(details, dict) else details
            return found if isinstance(found, list) else []
        return []

    # All releases at once: measured on the live stand, asking five together loses no more
    # of them than asking two, and the shorter the whole thing runs the fewer stalls it
    # meets. The count is bounded by LIMIT, so the fan can never be wider than the page.
    with ThreadPoolExecutor(max_workers=LIMIT) as pool:
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


#: Under which host name Prowlarr calls this adapter, and why a name and not an address.
#:
#: Prowlarr paces its asks per HOST and ignores the port, so two local adapters under one
#: host take turns: measured on the stand, a call that arrives in 0.01 s waited 2.01 s when
#: the neighbour had just been asked. The key is the host string as written, so a name of
#: our own buys a queue of our own on the very same plain loopback.
#:
#: 🔴 An address out of 127/8 will not do. 127.0.0.2 binds on Linux, where bind() consults a
#: route and the kernel puts all of 127/8 into the local table, but macOS in_pcbbind() wants
#: an exact interface address (ifa_ifwithaddr, netmask never read) and lo0 carries only
#: 127.0.0.1: bind() would answer EADDRNOTAVAIL, install.sh would print its warning and still
#: say it was done, and the AniLibria catalogue would be gone in silence. An `ifconfig lo0
#: alias` does not survive a reboot, so an installer step would not have fixed it either.
#: A client taking ::1 first (localhost resolves so on Debian and on macOS alike) is refused
#: on the loopback and goes on to 127.0.0.1 - measured on the stand.
HOST = "127.0.0.1"


def main() -> None:
    ThreadingHTTPServer(
        (HOST, int(sys.argv[1]) if len(sys.argv) > 1 else 9697), Handler
    ).serve_forever()


if __name__ == "__main__":
    main()
