"""The catalogue updater avoids a full archive download when the ETag is unchanged."""

import fcntl
import importlib.util
import io
import json
import signal
import subprocess
import sys
import urllib.error
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import NoReturn, get_type_hints
from urllib.request import Request

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_update", Path(__file__).parents[1] / "scripts/jacred-update.py"
)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def test_the_dynamic_builder_keeps_its_checked_build_contract() -> None:
    assert get_type_hints(updater._builder)["return"] is updater.Builder
    assert get_type_hints(updater.Builder.build)["return"] == tuple[int, float]


def test_an_unchanged_archive_keeps_the_live_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "index.sqlite"
    target.write_bytes(b"published")
    updater._etag_file(target).write_text('"old"\n')
    asked: list[str | None] = []

    def unchanged(request: Request, timeout: float) -> NoReturn:
        asked.append(request.get_header("If-none-match"))
        raise urllib.error.HTTPError("https://example.invalid", 304, "unchanged", Message(), None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", unchanged)

    assert updater.refresh(target) is None
    assert asked == ['"old"']
    assert target.read_bytes() == b"published"


@pytest.mark.parametrize("published", [None, b""])
def test_a_missing_or_empty_index_forces_an_unconditional_catalogue_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, published: bytes | None
) -> None:
    """An ETag alone cannot stand in for a catalogue the local adapter can read."""
    target = tmp_path / "index.sqlite"
    if published is not None:
        target.write_bytes(published)
    updater._etag_file(target).write_text('"old"\n')
    asked: list[str | None] = []

    class Archive(io.BytesIO):
        headers = Message()

        def __enter__(self) -> "Archive":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Builder:
        def build(
            self, _source: Path, _target: Path, _wait_for_idle: Callable[[], None] | None = None
        ) -> tuple[int, float]:
            return 1, 0.0

    class Brake:
        def wait(self) -> None:
            return None

    def download(request: Request, timeout: float) -> Archive:
        assert timeout == 1800
        asked.append(request.get_header("If-none-match"))
        return Archive(b"archive")

    monkeypatch.setattr(updater.urllib.request, "urlopen", download)
    monkeypatch.setattr(updater, "PlaybackBrake", Brake)
    monkeypatch.setattr(updater, "_unpack", lambda *_args: None)
    monkeypatch.setattr(updater, "_builder", lambda: Builder())

    assert updater.refresh(target) == (1, 0.0)
    assert asked == [None]


def test_download_uses_its_small_retry_ceiling_and_reraises_the_last_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    def broken(*_args: object, **_kwargs: object) -> NoReturn:
        nonlocal attempts
        attempts += 1
        raise OSError("connection lost")

    class Brake:
        def wait(self) -> None:
            return None

    assert updater.DOWNLOAD_TRIES == 3
    monkeypatch.setattr(updater.urllib.request, "urlopen", broken)

    with pytest.raises(OSError, match="connection lost"):
        updater._download(Request("https://example.invalid"), tmp_path / "latest.tar.zst", Brake())

    assert attempts == updater.DOWNLOAD_TRIES


def test_a_new_refresh_discards_work_left_by_an_interrupted_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A power loss must not let stale FileDB trees fill the next refresh's disk."""
    target = tmp_path / "index.sqlite"
    target.write_bytes(b"published")
    abandoned = tmp_path / "refresh-interrupted"
    abandoned.mkdir()
    (abandoned / "partial-filedb").write_bytes(b"incomplete")

    def unchanged(_request: Request, timeout: float) -> NoReturn:
        assert timeout == 1800
        raise urllib.error.HTTPError("https://example.invalid", 304, "unchanged", Message(), None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", unchanged)

    assert updater.refresh(target) is None
    assert not abandoned.exists()
    assert target.read_bytes() == b"published"


@pytest.mark.machine
def test_a_busy_refresh_leaves_the_running_work_and_new_index_alone(tmp_path: Path) -> None:
    """The timer and an install may meet, but only one may own this directory."""
    target = tmp_path / "index.sqlite"
    active = tmp_path / "refresh-active"
    active.mkdir()
    (active / "owner").write_text("still running", encoding="utf-8")
    fresh = target.with_suffix(".new")
    fresh.write_text("other refresh writes here", encoding="utf-8")
    lock = target.with_suffix(target.suffix + ".refresh.lock")
    assert updater.__file__ is not None

    with lock.open("a+") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        second = subprocess.run(
            [sys.executable, str(Path(updater.__file__)), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )

    assert second.returncode == 0, second.stderr
    assert second.stdout == "refresh already running\n"
    assert (active / "owner").read_text(encoding="utf-8") == "still running"
    assert fresh.read_text(encoding="utf-8") == "other refresh writes here"


def test_cleanup_leaves_a_neighbour_that_is_not_refresh_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "index.sqlite"
    abandoned = tmp_path / "refresh-interrupted"
    neighbour = tmp_path / "keep-this-directory"
    abandoned.mkdir()
    neighbour.mkdir()

    def unchanged(_request: Request, timeout: float) -> NoReturn:
        raise urllib.error.HTTPError("https://example.invalid", 304, "unchanged", Message(), None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", unchanged)

    assert updater.refresh(target) is None
    assert not abandoned.exists()
    assert neighbour.is_dir()


def test_refresh_keeps_the_brake_on_copy_unpack_and_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One refresh route holds all three brakes; deleting any one makes this fail."""
    events: list[str] = []
    signals: list[int] = []

    class Brake:
        def __init__(self) -> None:
            self._blocked = iter([True, False])

        def wait(self) -> None:
            events.append("wait")

        def blocked(self) -> bool:
            return next(self._blocked, False)

    brake = Brake()

    class Archive(io.BytesIO):
        headers = Message()

        def __enter__(self) -> "Archive":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Tar:
        pid = 41
        returncode: int | None = None
        polls = 0
        args = "tar"

        def poll(self) -> int | None:
            self.polls += 1
            if self.polls == 2:
                self.returncode = 0
            return self.returncode

        def wait(self) -> int:
            self.returncode = 0
            return 0

    class Builder:
        def build(
            self, _source: Path, _target: Path, wait: Callable[[], None] | None = None
        ) -> tuple[int, float]:
            assert getattr(wait, "__self__", None) is brake
            assert wait is not None
            wait()
            events.append("build")
            return 1, 0.0

    monkeypatch.setattr(updater, "PlaybackBrake", lambda: brake)
    monkeypatch.setattr(
        updater.urllib.request, "urlopen", lambda *_args, **_kwargs: Archive(b"x" * 2**21)
    )
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *_args, **_kwargs: Tar())
    monkeypatch.setattr(updater.os, "killpg", lambda _pid, signal: signals.append(signal))
    monkeypatch.setattr(updater.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(updater, "_builder", lambda: Builder())

    assert updater.refresh(tmp_path / "index.sqlite") == (1, 0.0)
    assert events == ["wait", "wait", "wait", "build"]
    assert signal.SIGSTOP in signals


def test_a_dropped_paused_download_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken:
        headers = Message()

        def __enter__(self) -> "Broken":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int = -1) -> bytes:
            raise OSError("server closed the idle connection")

    class Complete(io.BytesIO):
        headers = Message()

        def __enter__(self) -> "Complete":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    replies = iter([Broken(), Complete(b"complete archive")])
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: next(replies))

    class Brake:
        def wait(self) -> None:
            return None

    archive = tmp_path / "latest.tar.zst"
    assert updater._download(Request("https://example.invalid"), archive, Brake()) is None
    assert archive.read_bytes() == b"complete archive"


def test_interrupting_a_stopped_tar_continues_and_terminates_its_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signals: list[int] = []

    class Brake:
        def blocked(self) -> bool:
            return True

    class Tar:
        pid = 41
        returncode: int | None = None
        args = "tar"

        def poll(self) -> None:
            return None

        def wait(self) -> int:
            self.returncode = -signal.SIGTERM
            return self.returncode

    monkeypatch.setattr(updater.subprocess, "Popen", lambda *_args, **_kwargs: Tar())
    monkeypatch.setattr(updater.os, "killpg", lambda _pid, sent: signals.append(sent))

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(updater.time, "sleep", interrupt)

    with pytest.raises(KeyboardInterrupt):
        updater._unpack(tmp_path / "latest.tar.zst", tmp_path / "filedb", Brake())

    assert signals == [signal.SIGSTOP, signal.SIGCONT, signal.SIGTERM]


def test_state_probe_uses_the_bridge_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HA_PORT", "18479")

    assert updater._state() == "http://127.0.0.1:18479/api/state"


def test_playback_brake_has_a_three_hour_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long show yields the refresh only up to its declared 3-hour bound."""
    states = iter(["starting", "playing", "playing"])
    now = [0.0]
    slept: list[float] = []

    class State:
        def __enter__(self) -> "State":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int = -1) -> bytes:
            return json.dumps({"state": next(states)}).encode()

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *_args, **_kwargs: State())

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += 1

    brake = updater.PlaybackBrake(clock=lambda: now[0], sleep=sleep)

    assert brake.blocked() is True
    now[0] = updater.PAUSE_LIMIT
    assert brake.blocked() is False
    assert slept == []


def test_playback_brake_probes_the_state_at_most_four_times_a_second(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A million SQLite rows must not turn into a million HTTP requests."""
    now = [0.0]
    calls = 0

    class State:
        def __enter__(self) -> "State":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int = -1) -> bytes:
            return b'{"state":"playing"}'

    def state(*_args: object, **_kwargs: object) -> State:
        nonlocal calls
        calls += 1
        return State()

    monkeypatch.setattr(updater.urllib.request, "urlopen", state)
    brake = updater.PlaybackBrake(clock=lambda: now[0])

    assert brake.blocked() is True
    now[0] = updater.PAUSE_POLL / 2
    assert brake.blocked() is True
    assert calls == 1
    now[0] = updater.PAUSE_POLL
    assert brake.blocked() is True
    assert calls == 2
