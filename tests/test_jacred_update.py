"""The catalogue updater avoids a full archive download when the ETag is unchanged."""

import importlib.util
import json
import urllib.error
from email.message import Message
from pathlib import Path
from typing import NoReturn
from urllib.request import Request

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_update", Path(__file__).parents[1] / "scripts/jacred-update.py"
)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


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
