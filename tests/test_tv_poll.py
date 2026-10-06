"""Зеркало нити опроса каста на ТВ: заводится, гасится и не ждёт сама себя."""

from __future__ import annotations

import threading

from web.tv_poll import TvPoll


def test_disarm_stops_the_pump_and_waits_for_it() -> None:
    """После :meth:`TvPoll.disarm` нить кончилась: приёмник можно трогать."""
    poll, started, finished = TvPoll(), threading.Event(), threading.Event()

    def pump(stop: threading.Event) -> None:
        started.set()
        stop.wait(5.0)
        finished.set()

    poll.arm(pump)
    assert started.wait(5.0)
    poll.disarm(5.0)

    assert finished.is_set()


def test_the_pump_may_disarm_itself_without_joining_itself() -> None:
    """Опрос, снимающий каст сам, себя не ждёт: join своей же нити - ошибка."""
    poll, failed, done = TvPoll(), list[RuntimeError](), threading.Event()

    def pump(stop: threading.Event) -> None:
        try:
            poll.disarm(5.0)
        except RuntimeError as error:  # join своей нити поднимает именно его
            failed.append(error)
        done.set()

    poll.arm(pump)

    assert done.wait(5.0)
    assert failed == []


def test_disarm_without_a_pump_is_harmless() -> None:
    TvPoll().disarm(0.1)
