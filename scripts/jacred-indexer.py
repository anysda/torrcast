#!/usr/bin/env python3
"""Read-only Cardigann adapter for JacRed's public torrent search API."""

from __future__ import annotations

import calendar
import datetime
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import zip_longest
from typing import Any

# One origin, and that is measured, not overlooked: the catalog's other public names are
# not a second edge. One family serves an incomplete certificate chain and then tears the
# body mid-answer, another never answers, the rest no longer resolve. So the second way in
# is a second ROUTE to this same address rather than a second name - the shim row in
# install.sh carries it, because without a name in the handshake the address returns the
# very same answer.
ORIGINS = ("https://api.jacred.su",)
#: Cold answers of the API took 2.9-4.7 s on the stand (10 queries, 14-09-2026), and a cut of
#: 3 s turned them into an empty source. The first circle waits 6 s, so 5 s still lands.
#: torrcast reads an empty answer this late as a cut circle: keep ``ADAPTER_CUT`` in step.
TIMEOUT = 5.0
LIMIT = 100

# The adapter owns this request, so Prowlarr never sees or stores the personal
# key.  A non-default config path arrives from the installer in its service unit.
CONFIG_PATH = "/etc/torrcast/config.json"
_api_state = "untried"


def _key() -> str:
    """Read the current key without returning it to a caller or a log."""
    try:
        with open(os.environ.get("TORRCAST_CONFIG", CONFIG_PATH), encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError):
        return ""
    return raw.get("jacred_key", "") if isinstance(raw, dict) else ""


def _state(value: str) -> None:
    """Keep only the outcome class for local diagnostics, never a credential."""
    global _api_state
    _api_state = value


def _json(origin: str, query: str, year: int | None = None) -> Any:
    asked: dict[str, Any] = {"query": query, "sort": "sid", "limit": LIMIT}
    if year is not None:
        asked["year"] = year
    path = "/api/search?" + urllib.parse.urlencode(asked)
    headers = {"User-Agent": "torrcast/1"}
    if key := _key():
        headers["X-Api-Key"] = key
    request = urllib.request.Request(origin + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        _state("denied" if exc.code in {401, 403} else "failed")
        raise OSError(f"JacRed returned HTTP {exc.code}") from exc
    except OSError:
        _state("unreachable")
        raise
    _state("ok")
    return json.loads(body)


#: How the API is asked: the live `_json` in production, a stand-in under test.
Fetch = Callable[[str, str, int | None], Any]


#: What joins several texts of one request; torrcast's ``torrcast.domain.joint_query.JOINT``.
JOINT = " | "
#: Seconds the other texts of a joined request still get once its first text has answered.
#: Prowlarr History on the stand (06-30.09, 23835 texts asked of JacRed alone): a text still
#: answering past 1.0 s brought rows in 19.9% of all, past 1.5 s in 10.7%, past 2.0 s 4.9%.
#: Half a second it is: of 25 joined queries replayed on 02.10 the names brought new rows to
#: four, each inside 0.5 s of the text. The joined request ends the viewer's search, and 1.5 s
#: held it: cold searches on the stand (15 each, turn by turn) took 6.61 s, worst 8.83, against
#: 5.67 s, worst 6.61, with the same tiles and rows. A second each it is since the names go
#: in the year field too (06.10, 12 pictures twice): the field answers 0.5-1.3 s past the
#: text, and of 28 names that brought rows 6 landed inside 0.5 s, 21 inside 1.0, all in 1.5.
NAMES_GRACE = 1.0
#: Seconds from the request a name may still answer when the viewer's text filled `LIMIT`. Such
#: a text is cut, so the names are the only way to the asked picture: «Дюна» gave 100 rows,
#: 99 of «Часть вторая», and «Dune: Part One» of 2021 came only in the year field. On the stand
#: (06.10, 12 joined requests in turn) that name answered 0.65-1.32 s past the text, once
#: past the second, and the viewer got the YTS rows of another release with no Russian track.
#: Five, not four: such an answer is never empty, so torrcast's cut of an empty one does not
#: touch it, and it lands inside the first circle's six seconds. JacRed slows in spells: on the
#: stand (07.10, every request timed) four hung in 20 s and their second asks took 1.3-3.4 s;
#: «Король лев 1994» answered 4.80 s from the request, and four seconds lost «Дюна» of 2021.
#: An empty text waits as long: it holds nothing to keep the viewer waiting for. «Король Лев 2019»
#: (07.10) found nothing in 0.33 s, its names answered 1.8 and 2.7 s from the request, and a second
#: of grace left the viewer the YTS rows of the picture with no Russian track.
NAMES_DEADLINE = 5.0
#: Seconds the viewer's text waits before it is asked once more. On the stand (06.10) a text
#: alone answered in 0.46 s in the median and 0.64 at worst of 69, while one request in about 40
#: hung to the 5 s cut and the next, a few seconds later, answered in half a second: «Король
#: Лев» lost every Russian release so. A second ask past 1.5 s still lands inside `TIMEOUT`.
#: The names hang the same way: «Дюна» once got 96 rows past 4.7 s where it gets 215, the year
#: field had not answered by `NAMES_DEADLINE`. A name asked again at 1.5 s still lands before it.
ASK_AGAIN = 1.5


def search(query: str, fetch: Fetch = _json, grace: float = NAMES_GRACE) -> list[dict[str, Any]]:
    """Return usable magnets; an absent API is an empty optional source.

    `fetch` carries its production default, so the handler calls this with one argument
    and the behaviour is unchanged; a stand can hand in answers without a network.

    A query of several texts joined by `JOINT` is the picture's names asked at once:
    Prowlarr paces requests to one host two seconds apart, so the names come in one
    request and go to the API in parallel. The rows are interleaved text by text, so a
    cut of the joined answer by the caller's limit still keeps every text.

    The first text leads: torrcast puts the viewer's own there, and the others wait no more than
    `grace` past its answer, or till `NAMES_DEADLINE` when that answer is empty or filled `LIMIT`
    and so cannot hold the asked picture. Waiting all of them made the viewer's rows wait the
    slowest name, mostly empty: the joined request's median was 3.3 s where the text alone took
    0.65. The others leave only once it has answered: the API slows and refuses texts that come at
    once. On the stand (30.09, nine pairs in turn) the viewer's text asked with its two names took
    0.91 s in the median and was refused with 429 three times; asked first, 0.55 s and never
    refused. With all three at once torrcast's warm runs hit the 5 s cut 7 times in 15.
    """
    texts = [text.strip() for text in query.split(JOINT) if text.strip()]
    if len(texts) < 2:
        return _steady(query, fetch)[0]
    began = time.monotonic()
    first, full = _steady(texts[0], fetch)
    if full or not first:
        grace = max(grace, NAMES_DEADLINE - (time.monotonic() - began))
    forms = [form for text in texts[1:] for form in _forms(text)]
    pool = ThreadPoolExecutor(len(forms))
    asked = [pool.submit(_search, text, fetch, year) for text, year in forms]
    pool.shutdown(wait=False)  # a text past the grace ends on its own curl cut, unread
    wait(asked, timeout=grace)
    answers = [first, *(each.result() for each in asked if each.done())]
    rows: dict[str, dict[str, Any]] = {}
    for row in (row for tier in zip_longest(*answers) for row in tier if row is not None):
        rows.setdefault(row["magnet"], row)
    return list(rows.values())


#: A name text torrcast sends: the picture's name, then its year.
NAMED_YEAR = re.compile(r"(?P<name>.*\S)\s+(?P<year>(?:18|19|20)\d\d)")


def _forms(text: str) -> list[tuple[str, int | None]]:
    """Ask a name with its year both as the text and as the name in the API's year field.

    The API reads the year in the text as a word of the title, and most titles lack it:
    on the stand (06.10) «Дюна 2021» found only «Золотая дюна», «Dune: Part One 2021» and
    «Inception 2010» nothing, while the same names in the year field gave 26, 100 and 100
    rows of that year. The field alone is no answer either: «Брат» of 1997 gave 6 rows
    there and 66 as the text, most releases carry no year for the field.
    """
    named = NAMED_YEAR.fullmatch(text)
    if named is None:
        return [(text, None)]
    return [(text, None), (named["name"], int(named["year"]))]


def _steady(query: str, fetch: Fetch, year: int | None = None) -> tuple[list[dict[str, Any]], bool]:
    """One text, asked once more when its request hangs past `ASK_AGAIN`."""
    pool = ThreadPoolExecutor(2)
    asked = [pool.submit(_answered, query, fetch, year)]
    if not wait(asked, timeout=ASK_AGAIN).done:
        asked.append(pool.submit(_answered, query, fetch, year))
    pool.shutdown(wait=False)
    for each in as_completed(asked):  # the first rows, not the hung request's empty end
        if each.result()[0]:
            return each.result()
    return [], False


def _search(query: str, fetch: Fetch, year: int | None = None) -> list[dict[str, Any]]:
    return _steady(query, fetch, year)[0]


def _answered(
    query: str, fetch: Fetch, year: int | None = None
) -> tuple[list[dict[str, Any]], bool]:
    """The rows of one text, and whether the API cut its answer at `LIMIT`."""
    if not query.strip():
        return [], False
    for origin in ORIGINS:
        try:
            answer = fetch(origin, query, year)
        # HTTPException belongs here as much as OSError: a body cut short or a broken
        # status line leaves `urllib` as IncompleteRead or BadStatusLine, which are NOT
        # OSError. Uncaught it would leave the handler through a dropped connection, and
        # Prowlarr answers a dropped connection with a ban ladder - a stall of the source
        # would cost the catalog far more than the source itself is worth.
        except (OSError, http.client.HTTPException, ValueError):
            continue
        found = answer.get("results") if isinstance(answer, dict) else None
        if not isinstance(found, list):
            continue
        rows: list[dict[str, Any]] = []
        for item in found:
            if not isinstance(item, dict) or not item.get("title") or not item.get("magnet"):
                continue
            title = item["title"]
            if seasons := _seasons(item.get("seasons")):
                title += " [Сезон: " + ", ".join(str(number) for number in seasons) + "]"
            rows.append(
                {
                    "title": title,
                    "magnet": item["magnet"],
                    "size": item.get("size") or 0,
                    "seeders": item.get("seeders") or 0,
                    "leechers": item.get("peers") or 0,
                    "date": _unix(item.get("created_at")),
                }
            )
        return rows, len(found) >= LIMIT
    return [], False


def _unix(value: Any) -> str:
    """Give the release day as Unix seconds: Prowlarr reads those as they are.

    A plain "2009-06-02" goes through Prowlarr's guess at the format, and that cost ~40 ms of
    CPU a row on the stand (04.10, Prowlarr 2.5.2): 155 rows of "Вверх" took 6.1 s of CPU and
    7.05 s of answer, the same rows as seconds 0.04 s and 2.45 s. RuTor's 100 rows take 0.3 s.
    """
    try:
        day = datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return "0"
    return str(calendar.timegm(day.timetuple()))


def _seasons(value: Any) -> tuple[int, ...]:
    """Сделать факт JacRed частью имени, которое Prowlarr довозит до нашего разбора."""
    if not isinstance(value, list) or not all(
        isinstance(number, int) and 0 < number <= 40 for number in value
    ):
        return ()
    return tuple(dict.fromkeys(value))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/ping":
            body = b'{"status":"ok"}'
        elif parsed.path == "/status":
            body = json.dumps({"key": bool(_key()), "api": _api_state}).encode()
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
