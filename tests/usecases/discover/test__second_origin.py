"""Зеркало справки перед добором: спрошена вслепую, а номер части снимает с неё год."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._second_origin import _second_origin


class _Facts:
    """Справка, которая помнит, о чём и с каким типом её спросили - и когда.

    Ответ выдаётся ПО ТИПУ, а не по очереди спроса: вопросы уходят разом, и порядок, в
    котором они доедут, не назначен ничем. ``slow`` держит тип у себя названное число
    секунд - им и меряется, шли вопросы рядом или один за другим.
    """

    def __init__(
        self, *answers: tuple[bool | None, Origin], slow: dict[bool | None, float] | None = None
    ) -> None:
        self._answers = dict(answers)
        self._slow = slow or {}
        self._lock = threading.Lock()
        self.asked: list[tuple[str, bool | None, float]] = []
        self.spans: dict[bool | None, tuple[float, float]] = {}

    def __call__(self, name: str, **kwargs: Any) -> Origin:
        series: bool | None = kwargs["series"]
        start = time.monotonic()
        time.sleep(self._slow.get(series, 0.0))
        with self._lock:
            self.asked.append((name, series, kwargs["budget"]))
            self.spans[series] = (start, time.monotonic())
        return self._answers.get(series, Origin())


def _settle(name: str) -> None:
    """Дождаться уехавшего переспроса: в жизни его дописывает поток, в пробе - ждём мы.

    Счастливый путь переспрос НЕ ждёт - в этом и правка. Но проба, оставившая живой
    поток, покрасит соседнюю ложно, поэтому здесь его дожидаются явно, уже после того,
    как срок ответа замерен.
    """
    for thread in threading.enumerate():
        if thread.name == f"passport-blind-{name}":
            thread.join(5)


def test_the_year_of_the_facts_is_asked_blind() -> None:
    """Год выдачи справке не сообщают - иначе она подстроится и сверять станет нечего."""
    ask = _Facts((False, Origin(title="Cars", year=2006)))

    about = _second_origin(ask, "тачки", False, None, 1.5)

    assert about == Origin(title="Cars", year=2006)
    assert ("тачки", False, 1.5) in ask.asked
    assert {name for name, _kind, _budget in ask.asked} == {"тачки"}
    _settle("тачки")


def test_a_silent_answer_under_a_hinted_kind_is_asked_again_without_it() -> None:
    """🔴 TC-399. Тип подсказал вожак тощего пула и промолчал - отвечает переспрос без типа."""
    ask = _Facts((False, Origin()), (None, Origin(title="Serial Experiments Lain", year=1998)))

    about = _second_origin(ask, "lain", False, None, 1.5)

    assert about.title == "Serial Experiments Lain"
    assert sorted(str(kind) for _name, kind, _budget in ask.asked) == ["False", "None"]


@pytest.mark.machine
def test_both_asks_to_the_facts_leave_at_once_not_one_after_the_other() -> None:
    """Молчание под подсказкой не стоит второго срока справки подряд: спрашивают разом.

    Отрицательная проба на это - сама очередь: спроси справку по очереди, и переспрос
    уйдёт ПОСЛЕ того, как замолчит подсказка, а полсекунды сложатся в секунду.
    """
    ask = _Facts(
        (False, Origin()),
        (None, Origin(title="Serial Experiments Lain", year=1998)),
        slow={False: 0.3, None: 0.3},
    )

    start = time.monotonic()
    about = _second_origin(ask, "lain", False, None, 1.5)
    took = time.monotonic() - start

    assert about.title == "Serial Experiments Lain"
    (_typed_start, typed_end), (blind_start, _blind_end) = ask.spans[False], ask.spans[None]
    assert blind_start < typed_end, "переспрос ушёл только после того, как замолчала подсказка"
    assert took < 0.55, f"два вопроса по 0.3 с заняли {took:.2f} с - значит, шли по очереди"


@pytest.mark.machine
def test_an_answer_under_the_hint_does_not_wait_for_the_second_ask() -> None:
    """Под подсказкой ответили - переспрос доживает сам, и ответ человеку его не ждёт.

    Лишним от вопросов разом получается ЗАПРОС, а не секунда: ответ уехавшего переспроса
    допишет в справку его же поток (:class:`~torrcast.usecases.lookers.Lookers`).
    """
    ask = _Facts((False, Origin(title="Cars", year=2006)), slow={None: 1.0})

    start = time.monotonic()
    about = _second_origin(ask, "тачки", False, None, 1.5)
    took = time.monotonic() - start

    assert about == Origin(title="Cars", year=2006)
    assert took < 0.5, f"счастливый путь ждал молчащий переспрос {took:.2f} с"
    _settle("тачки")


def test_an_asked_part_number_strips_the_year_off_the_facts() -> None:
    """Справку зовут по имени франшизы, и год она называет ПЕРВОЙ картины, а не второй."""
    ask = _Facts((False, Origin(title="Cars", year=2006, name="Тачки", guessed=True)))

    about = _second_origin(ask, "тачки", False, 2, 1.5)

    assert about == Origin(title="Cars", year=None, name="Тачки", guessed=True)
    _settle("тачки")


def test_a_silent_answer_without_a_hint_is_not_asked_twice() -> None:
    """Типа не называли - переспрашивать нечем, второго вопроса к справке не бывает."""
    ask = _Facts()

    assert _second_origin(ask, "дедвуд", None, None, 1.5) == Origin()
    assert len(ask.asked) == 1
