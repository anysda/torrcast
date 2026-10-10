"""Снятие ждёт наше чтение, затем ограниченно ждёт читателей TorrServer."""

import threading
from pathlib import Path
from typing import Any

import pytest

from tests.fakes.clock import FakeClock
from torrcast.adapters.torrserver.describer import CACHE_DEADLINE, READERS_DEADLINE, Describer
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


class _Clock(FakeClock):
    """Фальшивые часы, которые не дают потоку снятия обогнать читателя."""

    def __init__(self) -> None:
        super().__init__(now=10.0)
        self.waiting = threading.Event()
        self.proceed = threading.Event()

    def sleep(self, seconds: float) -> None:
        self.waiting.set()
        assert self.proceed.wait(1), "проверка не отпустила поток снятия"
        super().sleep(seconds)


def _settler() -> threading.Thread:
    return next(thread for thread in threading.enumerate() if thread.name == f"settle-{KEY}")


def _close_while_reading(idle_after: int | None) -> tuple[list[float], int, _Clock]:
    """Снять раздачу посреди чтения; служба отпускает читателей с ``idle_after``-го опроса."""
    clock = _Clock()
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

    try:
        with READS.opened(URL, _Answer) as answer:
            assert answer is not None
            assert describer.close(KEY, remove, idle)
            assert clock.waiting.wait(1), "поток снятия не дошёл до барьера"
            assert removed == [], "живого читателя нельзя снимать из-под TorrServer"
            if idle_after is None:
                thread = _settler()
                clock.proceed.set()
                thread.join(1)
                assert not thread.is_alive(), "поток снятия остался ждать /cache"
                assert READS.stopped(URL), "срок должен остановить брошенное чтение"
                assert KEY not in describer._settling
        if idle_after is not None:
            clock.proceed.set()
            thread = _settler()
            thread.join(1)
            assert not thread.is_alive(), "снятие не завершилось после отпуска читателя"
    finally:
        READS.reopen(KEY)
    return removed, polls, clock


def test_the_removal_waits_for_the_service_to_release_the_readers_then_goes() -> None:
    removed, polls, _clock = _close_while_reading(idle_after=3)

    assert polls == 3
    assert removed == [pytest.approx(10.0 + 3 * 0.05)]


def test_a_hung_reader_and_cache_reader_end_at_the_deadlines_before_removing() -> None:
    """Мёртвый рой не оставляет ни поток снятия, ни ключ ``_settling`` навсегда."""
    removed, polls, _clock = _close_while_reading(idle_after=None)

    assert polls > 0
    assert removed == [pytest.approx(10.0 + READERS_DEADLINE + CACHE_DEADLINE)]


def test_without_our_reads_the_removal_goes_at_once_and_the_service_is_not_asked() -> None:
    describer = Describer(clock=FakeClock(now=10.0))
    asked: list[str] = []

    def idle() -> bool:
        asked.append(KEY)
        return True

    try:
        assert describer.close(KEY, lambda: True, idle) is True
        assert asked == []
    finally:
        READS.reopen(KEY)


class _Unwired:
    """Ответ без сокета: он на учёте, но принудительно закрыть в нём нечего."""

    def __enter__(self) -> "_Unwired":
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def test_a_torrent_added_again_while_the_service_releases_readers_is_not_removed() -> None:
    """Новый ``add`` посреди ожидания отпуска: ``rem`` уже чужой, он снял бы живую раздачу."""
    clock = _Clock()
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
            assert clock.waiting.wait(1), "поток снятия не дошёл до барьера"
        clock.proceed.set()
        thread = _settler()
        thread.join(1)
        assert not thread.is_alive(), "повторный add не завершил поток снятия"
        assert added_again
        assert removed == [], "rem ушёл по раздаче, которую добавили заново"
        assert not describer.dropped(KEY)
    finally:
        READS.reopen(KEY)
