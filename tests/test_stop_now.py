"""Зеркало остановки из чата: ``cast stop`` проходит и при занятом исполнителе."""

from __future__ import annotations

import threading
from typing import Any, cast

from tgbot.stop_now import StopNow
from torrcast.ports.abandon.slot import abandoned


class _Choice:
    def __init__(self) -> None:
        self.dropped = 0

    def drop(self) -> None:
        self.dropped += 1


class _Control:
    def __init__(self) -> None:
        self.cleaned = threading.Event()

    def clean(self) -> None:
        self.cleaned.set()


def test_a_free_executor_takes_the_stop_the_usual_way(_ports_restored: None) -> None:
    """Исполнитель свободен - остановка встаёт к нему, как и была, и отказа не ставит."""
    queued: list[list[str]] = []
    stops: list[int] = []

    def enqueue(args: list[str]) -> bool:
        queued.append(args)
        return True

    halt = StopNow(
        enqueue,
        cast(Any, _Choice()),
        cast(Any, _Control()),
        stop=lambda: stops.append(1),
    )

    halt()

    assert queued == [["stop"]]
    assert stops == []
    assert abandoned() is False


def test_a_busy_executor_still_stops_the_show_and_calls_off_the_raise(
    _ports_restored: None,
) -> None:
    """🔴 Прод 11-09-2026: на ``cast stop`` посреди долгого подъёма бот отвечал «занято».

    Теперь остановка идёт мимо очереди: показ гасится тем же вызовом, что у ``cast stop``,
    подъём узнаёт об отказе на своём повороте, ждущий выбор снимается.
    """
    choice, control = _Choice(), _Control()
    stopped = threading.Event()
    halt = StopNow(lambda args: False, cast(Any, choice), cast(Any, control), stop=stopped.set)

    halt()

    assert stopped.wait(2.0), "идущий показ не погашен"
    assert control.cleaned.wait(2.0), "пульт погашенного показа остался в чате"
    assert abandoned() is True, "идущий подъём о снятом заказе не узнал"
    assert choice.dropped == 1, "ждущий ответа выбор остался висеть"

    halt.forget()

    assert abandoned() is False, "отказ прошлого подъёма снял бы и следующий"
