#!/usr/bin/env python3
"""Refresh the local JacRed catalogue without ever calling its search API.

The publisher exposes the FileDB archive at this URL for self-hosted copies.  This
small updater only downloads that archive, builds a replacement SQLite file beside
the live one, and lets :mod:`jacred-index` publish it atomically.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

ARCHIVE = "https://jacred.su/database/latest.tar.zst"
BUILDER = Path(__file__).with_name("jacred-index.py")
STATE = "http://127.0.0.1:8479/api/state"
PAUSE_POLL = 0.25
PAUSE_LIMIT = 3 * 60 * 60


class Builder(Protocol):
    def build(
        self, source: Path, target: Path, wait_for_idle: Callable[[], None] | None = None
    ) -> tuple[int, float]: ...


class Readable(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class Writable(Protocol):
    def write(self, data: bytes) -> object: ...


class PlaybackBrake:
    """Yield FileDB work while the local viewer is starting or playing."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._paused_at: float | None = None
        self._next_probe = 0.0
        self._busy = False

    def blocked(self) -> bool:
        now = self._clock()
        if now >= self._next_probe:
            self._next_probe = now + PAUSE_POLL
            try:
                with urllib.request.urlopen(STATE, timeout=1) as response:
                    body = json.load(response)
            except (OSError, ValueError, json.JSONDecodeError):
                self._busy = False
            else:
                self._busy = isinstance(body, dict) and body.get("state") in {"starting", "playing"}
        if not self._busy:
            self._paused_at = None
            return False
        if self._paused_at is None:
            self._paused_at = now
        return now - self._paused_at < PAUSE_LIMIT

    def wait(self) -> None:
        while self.blocked():
            self._sleep(PAUSE_POLL)


def _builder() -> Builder:
    spec = importlib.util.spec_from_file_location("jacred_index", BUILDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Builder, module)


def _etag_file(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".etag")


def _discard_abandoned_refreshes(target: Path) -> None:
    """Free incomplete work left by a killed earlier refresh before making a new one."""
    for work in target.parent.glob("refresh-*"):
        if work.is_dir():
            shutil.rmtree(work)


def _copy(source: Readable, target: Writable, brake: PlaybackBrake) -> None:
    while block := source.read(1024 * 1024):
        brake.wait()
        target.write(block)


def _unpack(archive: Path, source: Path, brake: PlaybackBrake) -> None:
    process = subprocess.Popen(
        ["tar", "--zstd", "-xf", archive, "-C", source], start_new_session=True
    )
    paused = False
    while process.poll() is None:
        blocked = brake.blocked()
        if blocked and not paused:
            os.killpg(process.pid, signal.SIGSTOP)
            paused = True
        elif not blocked and paused:
            os.killpg(process.pid, signal.SIGCONT)
            paused = False
        time.sleep(PAUSE_POLL)
    if paused:
        os.killpg(process.pid, signal.SIGCONT)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args)


def refresh(target: Path) -> tuple[int, float] | None:
    """Fetch, unpack and atomically replace ``target``; keep the former index on errors."""
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    _discard_abandoned_refreshes(target)
    etag_file = _etag_file(target)
    brake = PlaybackBrake()
    headers = {"If-None-Match": etag_file.read_text().strip()} if etag_file.is_file() else {}
    request = urllib.request.Request(ARCHIVE, headers=headers)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix="refresh-") as temporary:
        work = Path(temporary)
        archive = work / "latest.tar.zst"
        try:
            with (
                urllib.request.urlopen(request, timeout=1800) as response,
                archive.open("wb") as out,
            ):
                _copy(response, out, brake)
                etag = response.headers.get("ETag")
        except urllib.error.HTTPError as error:
            if error.code == 304:
                return None
            raise
        source = work / "filedb"
        source.mkdir()
        _unpack(archive, source, brake)
        result = _builder().build(source, target, brake.wait)
        if etag:
            etag_file.write_text(etag + "\n")
        else:
            etag_file.unlink(missing_ok=True)
        return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: jacred-update.py INDEX.sqlite")
    result = refresh(Path(sys.argv[1]))
    if result is None:
        print("catalogue unchanged")
    else:
        rows, elapsed = result
        print(f"indexed {rows} releases in {elapsed:.1f} s")
