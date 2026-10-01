"""Уборка уступает замок отметок держателю, который его ждёт, и только ему."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator

import pytest

from tests.test_record_sweep import SLOW, _Base, _entries, _hash, _Holder, _Stuck
from torrcast.domain.continue_row import WARM_ROW
from torrcast.usecases.torrent_claims import CLAIMS
from web.record_sweep import record_sweep


def _third_holds() -> tuple[threading.Event, threading.Thread]:
    """Третий поток (``claimed`` страницы) держит замок, пока его не отпустят."""
    held, let_go = threading.Event(), threading.Event()

    def third() -> None:
        with CLAIMS._lock:
            held.set()
            let_go.wait(5)

    thread = threading.Thread(target=third)
    thread.start()
    assert held.wait(2)
    return let_go, thread


def _stands_in(thread: threading.Thread, function: str) -> None:
    """Дождаться, что поток встал на замок в ``function``: пауза очерёдности не гарантирует."""
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        frame = sys._current_frames().get(thread.ident or 0)
        if frame is not None and frame.f_code.co_name == function:
            time.sleep(0.02)
            return
        time.sleep(0.005)
    raise AssertionError(f"поток не встал на замок в {function}")


def _queued_behind_the_sweep() -> tuple[float, int]:
    """Уборка встала на замок первой, заводящий за ней; секунды ожидания и число сносов."""
    base, holder, ff = (
        _Stuck({_hash(n) for n in range(WARM_ROW + 4)}, answer=True),
        _Holder(),
        "e" * 40,
    )
    let_go, third = _third_holds()
    done: list[float] = []
    sweep = threading.Thread(
        target=record_sweep, args=(base, _entries(WARM_ROW + 4), lambda h: False)
    )
    sweep.start()
    _stands_in(sweep, "dropping")

    def add() -> None:
        CLAIMS.claim(ff, holder)
        done.append(time.monotonic())

    adder = threading.Thread(target=add)
    adder.start()
    _stands_in(adder, "_held")
    released = time.monotonic()
    let_go.set()
    adder.join(10)
    sweep.join(10)
    third.join(2)
    CLAIMS.unclaim(ff, holder)
    return done[0] - released, len(base.dropped)


@pytest.mark.machine
@pytest.mark.parametrize("trial", range(12))
def test_a_holder_queued_before_the_drop_waits_for_one_drop(trial: int) -> None:
    """🔴 Снос стирал метку держателя, вставшего на замок раньше, чем уборка его взяла.

    Проба 01-10-2026: третий поток держал замок, за ним встали уборка и заводящий; уборка
    взяла замок, стёрла метку и дальше её не видела, заводящий ждал все четыре сноса (1.6 с).
    """
    waited, dropped = _queued_behind_the_sweep()

    assert waited < SLOW + 0.25, (
        f"заход {trial}: заводящий ждал {waited:.2f} с, уборка снесла {dropped}"
    )


@pytest.fixture
def contended() -> Iterator[None]:
    """Держатель только что дождался замка за третьим потоком и отпустил его."""
    holder, ff = _Holder(), "d" * 40
    let_go, third = _third_holds()
    adder = threading.Thread(target=CLAIMS.claim, args=(ff, holder))
    adder.start()
    _stands_in(adder, "_held")
    let_go.set()
    adder.join(3)
    third.join(2)
    yield
    CLAIMS.unclaim(ff, holder)


@pytest.mark.machine
@pytest.mark.usefixtures("contended")
def test_a_sweep_after_a_served_waiter_goes_whole() -> None:
    """Дождавшийся держатель не числится в очереди: иначе уборка рвала бы каждый проход."""
    base = _Base({_hash(n) for n in range(WARM_ROW + 3)})

    gone, whole = record_sweep(base, _entries(WARM_ROW + 3), lambda h: False)

    assert not CLAIMS.waited()
    assert (len(gone), whole) == (3, True), "уборка уступает ушедшему держателю"
