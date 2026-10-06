#!/usr/bin/env python3
"""Keep Prowlarr's indexers matched to the reference roster written at install time.

An indexer whose tracker was unreachable when ``install.sh`` ran never got added:
Prowlarr validates the tracker on the ``POST`` and refuses a source it cannot reach.
The retry that runs right after install gives up within the hour, and nothing survives
a reboot. So the installer records every indexer it meant to have in a reference file
(``indexers.json``: one Prowlarr indexer body per entry), and this daemon walks that
file forever: each round it asks Prowlarr which indexers are live and re-POSTs the
bodies of the ones that are missing. Honesty is kept by Prowlarr itself - the ``POST``
runs its own live check, so a still-silent tracker is refused and simply retried next
round; a tracker that has come back answers and the indexer arrives on its own.

The first round waits ``TORRCAST_RECONCILE_DELAY`` seconds: the installer passes the span
of its own retry ladder, so a refused tracker is never asked twice at once (a second ask
in the same minute only extends the tracker's ban step).

Standalone on purpose: the installer drops it next to the shim and runs it under its own
service, so it loads like the shim does - by path, stdlib only, importing no project code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

_APIKEY = re.compile(r"<ApiKey>([^<]+)</ApiKey>")
_DEFAULT_EVERY = 900.0
_HTTP_TIMEOUT = 30.0
log = logging.getLogger("indexer-reconcile")


def read_apikey(config_path: str) -> str | None:
    """Prowlarr's API key, read from its own config.xml so no secret rides in the unit."""
    try:
        with open(config_path, encoding="utf-8", errors="replace") as handle:
            match = _APIKEY.search(handle.read())
    except OSError:
        return None
    return match.group(1).strip() if match else None


def load_manifest(path: str) -> list[dict[str, object]]:
    """Reference roster: a list of Prowlarr indexer bodies, each carrying its ``name``."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)]


def _get_json(url: str, apikey: str) -> object:
    request = urllib.request.Request(url, headers={"X-Api-Key": apikey})
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
        return json.load(response)


def live_names(url: str, apikey: str) -> set[str] | None:
    """Names Prowlarr already holds; ``None`` when it did not answer, so we skip this round."""
    try:
        payload = _get_json(f"{url}/api/v1/indexer", apikey)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    return {e["name"] for e in payload if isinstance(e, dict) and isinstance(e.get("name"), str)}


def _post(url: str, apikey: str, body: dict[str, object]) -> bool:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/api/v1/indexer",
        data=data,
        headers={"X-Api-Key": apikey, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT).close()
    except urllib.error.HTTPError:
        # Prowlarr's own tracker check refused it: the tracker is still unreachable.
        return False
    except (urllib.error.URLError, OSError):
        return False
    return True


def reconcile_once(url: str, apikey: str, manifest: list[dict[str, object]]) -> list[str]:
    """One pass: re-POST every reference indexer Prowlarr is missing. Returns names added."""
    present = live_names(url, apikey)
    if present is None:
        return []
    added: list[str] = []
    for entry in manifest:
        name = entry.get("name")
        if not isinstance(name, str) or name in present:
            continue
        if _post(url, apikey, entry):
            added.append(name)
            log.warning("added missing indexer %s", name)
    return added


def _run(
    url: str, config_path: str, manifest_path: str, every: float, once: bool, delay: float = 0.0
) -> int:
    if not once and delay > 0:
        time.sleep(delay)
    while True:
        apikey = read_apikey(config_path)
        if apikey:
            reconcile_once(url, apikey, load_manifest(manifest_path))
        else:
            log.warning("no Prowlarr API key in %s yet", config_path)
        if once:
            return 0
        time.sleep(every)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    url = os.environ.get("TORRCAST_PROWLARR_URL", "http://127.0.0.1:9696").rstrip("/")
    config_path = os.environ.get("TORRCAST_PROWLARR_CONFIG", "")
    manifest_path = os.environ.get("TORRCAST_INDEXER_MANIFEST", "")
    try:
        every = float(os.environ.get("TORRCAST_RECONCILE_EVERY", _DEFAULT_EVERY))
    except ValueError:
        every = _DEFAULT_EVERY
    try:
        delay = float(os.environ.get("TORRCAST_RECONCILE_DELAY", "0"))
    except ValueError:
        delay = 0.0
    if not config_path or not manifest_path:
        log.error("TORRCAST_PROWLARR_CONFIG and TORRCAST_INDEXER_MANIFEST are required")
        return 2
    once = "--once" in argv
    log.info(
        "reconcile start at %s: url=%s every=%.0fs first round after %.0fs manifest=%s",
        datetime.now(UTC).isoformat(timespec="seconds"),
        url,
        every,
        0.0 if once else delay,
        manifest_path,
    )
    return _run(url, config_path, manifest_path, every, once, delay)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
