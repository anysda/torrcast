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
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, runtime_checkable

ARCHIVE = "https://jacred.su/database/latest.tar.zst"
BUILDER = Path(__file__).with_name("jacred-index.py")
HA_PORT_ENV = "TORRCAST_HA_PORT"
PAUSE_POLL = 0.25
PAUSE_LIMIT = 3 * 60 * 60
DOWNLOAD_TRIES = 3


BUSY: Literal["busy"] = "busy"


class DownloadError(Exception):
    """The archive could not be fetched after the updater's retries."""


@runtime_checkable
class Builder(Protocol):
    """The part of the dynamically loaded index builder the updater uses."""

    def build(
        self, source: Path, target: Path, wait_for_idle: Callable[[], None] | None = None
    ) -> tuple[int, float]: ...


def _state() -> str:
    try:
        return f"http://127.0.0.1:{int(os.environ.get(HA_PORT_ENV) or 8479)}/api/state"
    except ValueError:
        return "http://127.0.0.1:8479/api/state"


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
                with urllib.request.urlopen(_state(), timeout=1) as response:
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
    assert isinstance(module, Builder)
    return module


def _etag_file(target: Path) -> Path:
    return target.with_suffix(target.suffix + ".etag")


def _discard_abandoned_refreshes(target: Path) -> None:
    """Free incomplete work left by a killed earlier refresh before making a new one."""
    for work in target.parent.glob("refresh-*"):
        if work.is_dir():
            shutil.rmtree(work)


def _copy(source: BinaryIO, target: BinaryIO, brake: PlaybackBrake) -> None:
    while block := source.read(1024 * 1024):
        brake.wait()
        target.write(block)


def _unpack(archive: Path, source: Path, brake: PlaybackBrake) -> None:
    process = subprocess.Popen(
        ["tar", "--zstd", "-xf", archive, "-C", source], start_new_session=True
    )
    paused = False
    try:
        while process.poll() is None:
            blocked = brake.blocked()
            if blocked and not paused:
                os.killpg(process.pid, signal.SIGSTOP)
                paused = True
            elif not blocked and paused:
                os.killpg(process.pid, signal.SIGCONT)
                paused = False
            time.sleep(PAUSE_POLL)
    except BaseException:
        if paused:
            os.killpg(process.pid, signal.SIGCONT)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()
        raise
    if paused:
        os.killpg(process.pid, signal.SIGCONT)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args)


def _download(request: urllib.request.Request, archive: Path, brake: PlaybackBrake) -> str | None:
    """Restart an interrupted paused download instead of publishing a partial archive."""
    for attempt in range(DOWNLOAD_TRIES):
        try:
            with (
                urllib.request.urlopen(request, timeout=1800) as response,
                archive.open("wb") as out,
            ):
                _copy(response, out, brake)
                etag = response.headers.get("ETag")
                return etag if isinstance(etag, str) else None
        except urllib.error.HTTPError:
            raise
        except OSError:
            if attempt + 1 == DOWNLOAD_TRIES:
                raise
    raise AssertionError("unreachable")


def refresh(target: Path) -> tuple[int, float] | Literal["busy"] | None:
    """Fetch, unpack and atomically replace ``target``; keep the former index on errors."""
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    with target.with_suffix(target.suffix + ".refresh.lock").open("a+") as lock:
        try:
            flock(lock, LOCK_EX | LOCK_NB)
        except BlockingIOError:
            return BUSY
        _discard_abandoned_refreshes(target)
        etag_file = _etag_file(target)
        brake = PlaybackBrake()
        has_index = target.is_file() and target.stat().st_size > 0
        headers = (
            {"If-None-Match": etag_file.read_text().strip()}
            if has_index and etag_file.is_file()
            else {}
        )
        request = urllib.request.Request(ARCHIVE, headers=headers)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix="refresh-") as temporary:
            work = Path(temporary)
            archive = work / "latest.tar.zst"
            try:
                etag = _download(request, archive, brake)
            except urllib.error.HTTPError as error:
                if error.code == 304:
                    return None
                raise DownloadError from error
            except OSError as error:
                raise DownloadError from error
            source = work / "filedb"
            source.mkdir()
            _unpack(archive, source, brake)
            result = _builder().build(source, target, brake.wait)
            if etag:
                etag_file.write_text(etag + "\n")
            else:
                etag_file.unlink(missing_ok=True)
            return result


def _say(english: str, russian: str, *, error: bool = False) -> None:
    print(
        russian if os.environ.get("TORRCAST_LANGUAGE") == "ru" else english,
        file=sys.stderr if error else sys.stdout,
    )


def main() -> int:
    if len(sys.argv) != 2:
        _say(
            "usage: jacred-update.py INDEX.sqlite",
            "использование: jacred-update.py INDEX.sqlite",
            error=True,
        )
        return 2
    try:
        result = refresh(Path(sys.argv[1]))
    except DownloadError:
        _say("could not download the JacRed catalogue", "не скачался каталог JacRed", error=True)
        return 1
    except FileNotFoundError:
        _say("JacRed catalogue source disappeared", "пропал источник каталога JacRed", error=True)
        return 1
    except ValueError as error:
        if str(error) != "FileDB contains no usable releases":
            _say(
                "could not refresh the JacRed catalogue", "не обновился каталог JacRed", error=True
            )
        else:
            _say(
                "JacRed catalogue has no usable releases",
                "в каталоге JacRed нет пригодных раздач",
                error=True,
            )
        return 1
    except Exception:
        _say("could not refresh the JacRed catalogue", "не обновился каталог JacRed", error=True)
        return 1
    if result == BUSY:
        _say("refresh already running", "обновление уже запущено")
    elif result is None:
        _say("catalogue unchanged", "каталог не изменился")
    else:
        rows, elapsed = result
        _say(
            f"indexed {rows} releases in {elapsed:.1f} s",
            f"проиндексировано {rows} раздач за {elapsed:.1f} с",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
