"""Подъём погасшего показа: только на свободном экране и с честной секундой в ответе."""

from __future__ import annotations

from tests.adapters.chromecast.cast.wired import Device, Quiet
from torrcast.adapters.chromecast.cast.replay import _replay
from torrcast.domain.not_raised import NOT_RAISED


def test_a_successful_resurrection_answers_with_the_second_it_actually_started_from() -> None:
    """Ноль - законное место фильма, поэтому отказ отвечает отрицательной секундой.

    Пока оба ответа были нулём, удачный подъём с начала картины уходил в ленту как
    «приёмник показ не взял» - при идущей картинке.
    """
    receiver = Quiet()

    assert _replay(receiver, 0.0) == 0.0
    assert receiver.loads == [0.0]
    assert receiver.budgets == [receiver.WAKE_TIMEOUT]


def test_a_foreign_show_on_the_screen_is_never_interrupted() -> None:
    """Пока нас не было, на том же ТВ могли начать смотреть что-то другое."""
    receiver = Quiet(device=Device(app="чужое"))

    assert _replay(receiver, 100.0) == NOT_RAISED
    assert receiver.restarts == 0
    assert receiver.loads == []
    assert receiver.refusal().startswith("нельзя:"), "не поднял, ПОТОМУ ЧТО НЕЛЬЗЯ"


def test_a_receiver_that_did_not_take_the_load_says_so() -> None:
    """Картинки нет - это отказ, и зовущий попробует ещё раз или честно погасит показ."""
    receiver = Quiet(settles=False)

    assert _replay(receiver, 100.0) == NOT_RAISED
    assert receiver.refusal().startswith("не взял:")


def test_a_receiver_that_is_not_in_the_network_does_not_blow_up_the_caller() -> None:
    """Приёмника может не быть в сети вовсе, а это уже не авария показа."""
    receiver = Quiet(breaks=True)

    assert _replay(receiver, 100.0) == NOT_RAISED
    assert receiver.refusal().startswith("упал:"), "не поднял, ПОТОМУ ЧТО УПАЛ"


def test_the_three_ways_of_not_raising_the_show_are_named_apart() -> None:
    """🔴 «Нельзя», «упал» и «не взял» - три события с тремя выводами, а не одно.

    Пока все три отвечали одним :data:`NOT_RAISED` и уходили в ленту одним ``ok=False``,
    замер подъёмов приёмника читался двусмысленно: занятый чужим показом ТВ и легшее
    соединение стояли там одной строкой. Ответ у них и правда один - картинки нет, -
    поэтому различие обязано жить не в нём, а в названной причине.
    """
    said = [
        _named(Quiet(device=Device(app="чужое"))),
        _named(Quiet(breaks=True)),
        _named(Quiet(settles=False)),
    ]

    assert len(set(said)) == 3, f"три отказа обязаны называться по-разному: {said}"


def test_a_successful_resurrection_leaves_no_stale_reason_behind() -> None:
    """Причина прошлого отказа не имеет права пережить удавшийся подъём."""
    receiver = Quiet(settles=False)
    _replay(receiver, 100.0)
    receiver.settles = True

    assert _replay(receiver, 100.0) == 100.0
    assert receiver.refusal() == ""


def _named(receiver: Quiet) -> str:
    """Как приёмник назвал причину несостоявшегося подъёма."""
    assert _replay(receiver, 100.0) == NOT_RAISED
    return receiver.refusal()


def test_the_answer_is_the_place_past_the_deadly_segment_and_not_the_place_asked_for() -> None:
    """Показ, умирающий на одном куске, поднимают уже за ним - это до пятнадцати секунд.

    Пока метод отвечал «да/нет», сказать о подъёме мог только тот, кто просил, - и
    говорил он про место, где показ как раз НЕ пошёл.
    """
    receiver = Quiet()
    receiver.next_cut = lambda at: 137.095 if at < 137.095 else 152.0
    receiver._deaths[137.095] = receiver.DEADLY_TRIES - 1

    started = _replay(receiver, 127.2)

    assert started > 127.2
    assert receiver.loads == [started]
    assert receiver._peak == started and receiver._at == started


def test_a_paused_resurrection_loads_without_autoplay() -> None:
    """Паузу ставил зритель: сессию возвращают на закладку, НЕ начиная показ."""
    receiver = Quiet()

    assert _replay(receiver, 2231.0, paused=True) == 2231.0
    assert receiver.loads == [2231.0]
    assert receiver.paused_loads == [True]


def test_the_watchdog_starts_the_new_session_from_a_clean_slate() -> None:
    """Сессия новая, и подвисы прошлой к ней отношения не имеют."""
    receiver = Quiet()
    receiver._reloads, receiver._stall_hits, receiver._blind = 2, 4, 3
    receiver._gone, receiver._skip_from = True, 100.0

    _replay(receiver, 500.0)

    assert (receiver._reloads, receiver._stall_hits, receiver._blind) == (0, 0, 0)
    assert receiver._gone is False
    assert receiver._skip_from == -1.0, "о перешагнутом куске вторым голосом незачем"
