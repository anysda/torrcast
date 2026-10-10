"""Снятие при нашем идущем чтении: обрыв сразу, ``rem`` после отпуска читателей службой."""

import threading
from pathlib import Path
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.describer import READERS_DEADLINE, Describer
from torrcast.adapters.torrserver.stream_reads import READS

KEY = "0123456789abcdef0123456789abcdef01234567"
URL = f"http://torrserver/stream?link={KEY}&index=1&play"


@pytest.fixture(autouse=True)
def _state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


class _Answer:
    def __enter__(self) -> "_Answer":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def _close_while_reading(idle_after: int | None) -> tuple[list[float], int, FakeClock]:
    """Снять раздачу посреди чтения; служба отпускает читателей с ``idle_after``-го опроса."""
    clock = FakeClock(now=10.0)
    describer = Describer(clock=clock)
    removed: list[float] = []
    polls = 0

    def idle() -> bool:
        nonlocal polls
        polls += 1
        return idle_after is not None and polls >= idle_after

    def remove() -> bool:
        removed.append(clock.monotonic())
        return True

    with READS.opened(URL, _Answer) as answer:
        assert answer is not None
        assert describer.close(KEY, remove, idle)
        assert removed == [], "живого читателя нельзя снимать из-под TorrServer"
    for thread in threading.enumerate():
        if thread.name == f"settle-{KEY}":
            thread.join(5)
    READS.reopen(KEY)
    return removed, polls, clock


def test_the_removal_waits_for_the_service_to_release_the_readers_then_goes() -> None:
    removed, polls, _clock = _close_while_reading(idle_after=3)

    assert polls == 3
    assert removed == [pytest.approx(10.0 + 2 * 0.05)]


def test_a_hung_reader_is_stopped_at_the_deadline_before_removing() -> None:
    """Сосед не держит новый показ вечно: его поток сперва закрывают безопасно."""
    clock = FakeClock(now=10.0)
    describer = Describer(clock=clock)
    removed: list[float] = []
    polls = 0

    def idle() -> bool:
        nonlocal polls
        polls += 1
        return polls >= 3

    with READS.opened(URL, _Answer) as answer:
        assert answer is not None
        assert describer.close(KEY, lambda: removed.append(clock.monotonic()) or True, idle)
        for thread in threading.enumerate():
            if thread.name == f"settle-{KEY}":
                thread.join(5)
        assert READS.stopped(URL), "срок должен остановить брошенное чтение"
        assert removed == [pytest.approx(10.0 + READERS_DEADLINE + 2 * 0.05)]
    READS.reopen(KEY)


def test_without_our_reads_the_removal_goes_at_once_and_the_service_is_not_asked() -> None:
    describer = Describer(clock=FakeClock(now=10.0))
    asked: list[str] = []

    def idle() -> bool:
        asked.append(KEY)
        return True

    assert describer.close(KEY, lambda: True, idle) is True
    assert asked == []
    READS.reopen(KEY)


class _Unwired:
    """Ответ без сокета: на учёте стоит, рвать в нём нечего, ``cut`` всё равно ``True``."""

    def __enter__(self) -> "_Unwired":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def test_a_torrent_added_again_while_the_service_releases_readers_is_not_removed() -> None:
    """Новый ``add`` посреди ожидания отпуска: ``rem`` уже чужой, он снял бы живую раздачу."""
    clock = FakeClock(now=10.0)
    describer = Describer(clock=clock)
    removed: list[float] = []
    added_again = False

    def idle() -> bool:
        nonlocal added_again
        describer.later("http://torrserver", KEY)  # повторное добавление той же раздачи
        added_again = True
        return True

    def remove() -> bool:
        removed.append(clock.monotonic())
        return True

    try:
        with READS.opened(URL, lambda: _Unwired()) as answer:
            assert answer is not None
            assert describer.close(KEY, remove, idle)
        for thread in threading.enumerate():
            if thread.name == f"settle-{KEY}":
                thread.join(5)
        assert added_again
        assert removed == [], "rem ушёл по раздаче, которую добавили заново"
        assert not describer.dropped(KEY)
    finally:
        READS.reopen(KEY)
