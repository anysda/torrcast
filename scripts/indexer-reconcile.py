#!/usr/bin/env python3
"""Add the indexers the installer meant to have once their trackers answer again.

An indexer whose tracker was unreachable when ``install.sh`` ran never got added:
Prowlarr validates the tracker on the ``POST`` and refuses a source it cannot reach.
The retry that runs right after install gives up within the hour, and nothing survives
a reboot. So the installer records every indexer it set out to add in an owed list
(``indexers.json``: one Prowlarr indexer body per entry), and this daemon walks that
list forever. Honesty is kept by Prowlarr itself - the ``POST`` runs its own live check,
so a still-silent tracker is refused and simply asked again next round.

The list holds what is still owed, not what should exist. An entry Prowlarr holds (even
switched off) is crossed out on sight, so an indexer a human deletes later stays deleted.
An entry marked ``"retry": false`` is a narrow source: it is asked once per install and
never here, since each ask at a silent tracker extends its ban and the catalogue does
not miss it. It stays listed so ``cast doctor`` can still name it.

Trackers are not asked while the installer's own background retries run (their pids are
in ``TORRCAST_LATE_PIDS``): two asks in the same minute only extend a tracker's ban.
After a reboot those retries are gone, and the first round runs at once.

Standalone on purpose: the installer drops it next to the shim and runs it under its own
service, so it loads like the shim does - by path, stdlib only, importing no project code.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

_APIKEY = re.compile(r"<ApiKey>([^<]+)</ApiKey>")
_DEFAULT_EVERY = 900.0
#: How often Prowlarr's list is read to cross out what arrived or was set up by hand.
_LOOK_EVERY = 60.0
_HTTP_TIMEOUT = 30.0
#: Background jobs of ``install.sh`` that ask trackers to add an indexer.
_ASKING_JOBS = frozenset({"add_indexers", "add_twins", "retry_add_indexers"})
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
    """Owed list: Prowlarr indexer bodies, each carrying its ``name``."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)]


def cross_out(path: str, names: set[str]) -> None:
    """Drop ``names`` from the owed list, re-read right before the write and swapped in whole."""
    entries = load_manifest(path)
    keep = [e for e in entries if e["name"] not in names]
    if len(keep) == len(entries):
        return
    with open(f"{path}.tmp", "w", encoding="utf-8") as handle:
        json.dump(keep, handle, indent=2)
    os.chmod(f"{path}.tmp", 0o644)
    os.replace(f"{path}.tmp", path)


def _started(pid: str) -> str:
    env = {"LC_ALL": "C", "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    try:
        done = subprocess.run(
            ["ps", "-o", "lstart=", "-p", pid], capture_output=True, text=True, env=env, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def install_retrying(pids_path: str) -> list[str]:
    """Pids of the installer's background adds still alive; a reused pid does not count."""
    try:
        with open(pids_path, encoding="utf-8") as handle:
            rows = [line.rstrip("\n").split("\t") for line in handle]
    except OSError:
        return []
    return [
        row[0]
        for row in rows
        if len(row) == 3 and row[2] in _ASKING_JOBS and row[1] and _started(row[0]) == row[1]
    ]


def live_names(url: str, apikey: str) -> set[str] | None:
    """Names Prowlarr already holds; ``None`` when it did not answer, so we skip this round."""
    request = urllib.request.Request(f"{url}/api/v1/indexer", headers={"X-Api-Key": apikey})
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    return {e["name"] for e in payload if isinstance(e, dict) and isinstance(e.get("name"), str)}


def _post(url: str, apikey: str, body: dict[str, object]) -> bool:
    body = {k: v for k, v in body.items() if k != "retry"}
    request = urllib.request.Request(
        f"{url}/api/v1/indexer",
        data=json.dumps(body).encode("utf-8"),
        headers={"X-Api-Key": apikey, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT).close()
    except (urllib.error.URLError, OSError):
        # HTTPError included: Prowlarr's own tracker check refused it.
        return False
    return True


def reconcile_once(url: str, apikey: str, manifest_path: str, ask: bool = True) -> list[str]:
    """Cross out what Prowlarr holds; with ``ask``, re-POST the owed retried ones. Returns added."""
    present = live_names(url, apikey)
    if present is None:
        return []
    owed = load_manifest(manifest_path)
    done = {e["name"] for e in owed if e["name"] in present}
    added: list[str] = []
    for entry in owed:
        name = str(entry["name"])
        if not ask or name in done or entry.get("retry") is False:
            continue
        if _post(url, apikey, entry):
            added.append(name)
            log.warning("added missing indexer %s", name)
        else:
            log.info("%s still refused by its tracker; asking again in the next round", name)
    if done or added:
        cross_out(manifest_path, done | set(added))
    return added


def _run(url: str, config_path: str, manifest_path: str, pids_path: str, every: float) -> int:
    due = 0.0
    waiting: list[str] = []
    while True:
        busy = install_retrying(pids_path)
        if busy != waiting and busy:
            log.info("installer retries still running (pid %s): trackers wait", " ".join(busy))
        waiting = busy
        ask = time.monotonic() >= due and not busy
        apikey = read_apikey(config_path)
        if apikey:
            reconcile_once(url, apikey, manifest_path, ask=ask)
        else:
            log.warning("no Prowlarr API key in %s yet", config_path)
        if ask:
            due = time.monotonic() + every
        wait = due - time.monotonic()
        time.sleep(min(_LOOK_EVERY, wait) if wait >= 1.0 else _LOOK_EVERY)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    url = os.environ.get("TORRCAST_PROWLARR_URL", "http://127.0.0.1:9696").rstrip("/")
    config_path = os.environ.get("TORRCAST_PROWLARR_CONFIG", "")
    manifest_path = os.environ.get("TORRCAST_INDEXER_MANIFEST", "")
    pids_path = os.environ.get("TORRCAST_LATE_PIDS", "")
    try:
        every = float(os.environ.get("TORRCAST_RECONCILE_EVERY", _DEFAULT_EVERY))
    except ValueError:
        every = _DEFAULT_EVERY
    if not config_path or not manifest_path:
        log.error("TORRCAST_PROWLARR_CONFIG and TORRCAST_INDEXER_MANIFEST are required")
        return 2
    if "--once" in argv:
        apikey = read_apikey(config_path)
        if apikey:
            reconcile_once(url, apikey, manifest_path, ask=not install_retrying(pids_path))
        return 0
    log.info("reconcile start: url=%s every=%.0fs manifest=%s", url, every, manifest_path)
    return _run(url, config_path, manifest_path, pids_path, every)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
