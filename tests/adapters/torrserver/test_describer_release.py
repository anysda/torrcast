"""Снятие при нашем идущем чтении: обрыв сразу, ``rem`` после отпуска читателей службой."""

import socket
import threading
from pathlib import Path
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.describer import RELEASE, Describer
from torrcast.adapters.torrserver.stream_reads import READS

KEY = "0123456789abcdef0123456789abcdef01234567"
URL = f"http://torrserver/stream?link={KEY}&index=1&play"


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


class _Answer:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def __enter__(self) -> "_Answer":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def fileno(self) -> int:
        return self._sock.fileno()


def _close_while_reading(idle_after: int | None) -> tuple[list[float], int, bytes, FakeClock]:
    """Снять раздачу посреди чтения; служба отпускает читателей с ``idle_after``-го опроса."""
    clock = FakeClock(now=10.0)
    describer = Describer(clock=clock)
    ours, service = socket.socketpair()
    removed: list[float] = []
    polls = 0

    def idle() -> bool:
        nonlocal polls
        polls += 1
        return idle_after is not None and polls >= idle_after

    def remove() -> bool:
        removed.append(clock.monotonic())
        return True

    with READS.opened(URL, lambda: _Answer(ours)) as answer:
        assert answer is not None
        assert describer.close(KEY, remove, idle)
        service.settimeout(3)
        hangup = service.recv(1)
        for thread in threading.enumerate():
            if thread.name == f"settle-{KEY}":
                thread.join(5)
    READS.reopen(KEY)
    ours.close()
    service.close()
    return removed, polls, hangup, clock


def test_the_removal_waits_for_the_service_to_release_the_readers_then_goes() -> None:
    removed, polls, hangup, _clock = _close_while_reading(idle_after=3)

    assert hangup == b""  # наше соединение оборвано до rem
    assert polls == 3
    assert removed == [pytest.approx(10.0 + 2 * 0.05)]


def test_a_reader_the_service_never_releases_does_not_hold_the_removal_past_the_bound() -> None:
    removed, _polls, _hangup, _clock = _close_while_reading(idle_after=None)

    assert len(removed) == 1
    assert 10.0 + RELEASE <= removed[0] < 10.0 + RELEASE + 0.1


def test_without_our_reads_the_removal_goes_at_once_and_the_service_is_not_asked() -> None:
    describer = Describer(clock=FakeClock(now=10.0))
    asked: list[str] = []

    def idle() -> bool:
        asked.append(KEY)
        return True

    assert describer.close(KEY, lambda: True, idle) is True
    assert asked == []
    READS.reopen(KEY)
