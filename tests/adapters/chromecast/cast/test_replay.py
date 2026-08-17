"""Подъём погасшего показа: только на свободном экране и с честной секундой в ответе."""

from __future__ import annotations

from typing import Any

from tests.adapters.chromecast.cast.wired import Device, Wired
from torrcast.adapters.chromecast.cast.replay import _replay
from torrcast.domain.not_raised import NOT_RAISED


class _Quiet(Wired):
    """Приёмник, у которого подъём приложения и ожидание картинки только записываются."""

    def __init__(self, settles: bool = True, breaks: bool = False, **rest: Any) -> None:
        super().__init__(**rest)
        self.settles = settles
        self.breaks = breaks
        self.loads: list[float] = []
        self.budgets: list[float] = []
        self.restarts = 0

    def _restart_app(self) -> None:
        self.restarts += 1
        if self.breaks:
            raise OSError("приёмника нет в сети")

    def _load(self, at: float = 0.0) -> None:
        self.loads.append(at)

    def _settle(self, budget: float) -> bool:
        self.budgets.append(budget)
        return self.settles


def test_a_successful_resurrection_answers_with_the_second_it_actually_started_from() -> None:
    """Ноль - законное место фильма, поэтому отказ отвечает отрицательной секундой.

    Пока оба ответа были нулём, удачный подъём с начала картины уходил в ленту как
    «приёмник показ не взял» - при идущей картинке.
    """
    receiver = _Quiet()

    assert _replay(receiver, 0.0) == 0.0
    assert receiver.loads == [0.0]
    assert receiver.budgets == [receiver.WAKE_TIMEOUT]


def test_a_foreign_show_on_the_screen_is_never_interrupted() -> None:
    """Пока нас не было, на том же ТВ могли начать смотреть что-то другое."""
    receiver = _Quiet(device=Device(app="чужое"))

    assert _replay(receiver, 100.0) == NOT_RAISED
    assert receiver.restarts == 0
    assert receiver.loads == []


def test_a_receiver_that_did_not_take_the_load_says_so() -> None:
    """Картинки нет - это отказ, и зовущий попробует ещё раз или честно погасит показ."""
    receiver = _Quiet(settles=False)

    assert _replay(receiver, 100.0) == NOT_RAISED


def test_a_receiver_that_is_not_in_the_network_does_not_blow_up_the_caller() -> None:
    """Приёмника может не быть в сети вовсе, а это уже не авария показа."""
    receiver = _Quiet(breaks=True)

    assert _replay(receiver, 100.0) == NOT_RAISED


def test_the_answer_is_the_place_past_the_deadly_segment_and_not_the_place_asked_for() -> None:
    """Показ, умирающий на одном куске, поднимают уже за ним - это до пятнадцати секунд.

    Пока метод отвечал «да/нет», сказать о подъёме мог только тот, кто просил, - и
    говорил он про место, где показ как раз НЕ пошёл.
    """
    receiver = _Quiet()
    receiver.next_cut = lambda at: 137.095 if at < 137.095 else 152.0
    receiver._deaths[137.095] = receiver.DEADLY_TRIES - 1

    started = _replay(receiver, 127.2)

    assert started > 127.2
    assert receiver.loads == [started]
    assert receiver._peak == started and receiver._at == started


def test_the_watchdog_starts_the_new_session_from_a_clean_slate() -> None:
    """Сессия новая, и подвисы прошлой к ней отношения не имеют."""
    receiver = _Quiet()
    receiver._reloads, receiver._stall_hits, receiver._blind = 2, 4, 3
    receiver._gone, receiver._skip_from = True, 100.0

    _replay(receiver, 500.0)

    assert (receiver._reloads, receiver._stall_hits, receiver._blind) == (0, 0, 0)
    assert receiver._gone is False
    assert receiver._skip_from == -1.0, "о перешагнутом куске вторым голосом незачем"
