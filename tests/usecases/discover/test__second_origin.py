"""Зеркало справки перед добором: спрошена вслепую, а номер части снимает с неё год."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._second_origin import _second_origin


class _Facts:
    """Справка, которая помнит, о чём и с каким типом её спросили."""

    def __init__(self, *answers: Origin) -> None:
        self._answers = list(answers)
        self.asked: list[tuple[str, bool | None, float]] = []

    def __call__(self, name: str, **kwargs: Any) -> Origin:
        self.asked.append((name, kwargs["series"], kwargs["budget"]))
        return self._answers.pop(0) if self._answers else Origin()


def test_the_year_of_the_facts_is_asked_blind() -> None:
    """Год выдачи справке не сообщают - иначе она подстроится и сверять станет нечего."""
    ask = _Facts(Origin(title="Cars", year=2006))

    about = _second_origin(ask, "тачки", False, None, 1.5)

    assert about == Origin(title="Cars", year=2006)
    assert ask.asked == [("тачки", False, 1.5)]


def test_a_silent_answer_under_a_hinted_kind_is_asked_again_without_it() -> None:
    """🔴 TC-399. Тип подсказал вожак тощего пула и промолчал - переспрашивают без типа."""
    ask = _Facts(Origin(), Origin(title="Serial Experiments Lain", year=1998))

    about = _second_origin(ask, "lain", False, None, 1.5)

    assert about.title == "Serial Experiments Lain"
    assert [kind for _name, kind, _budget in ask.asked] == [False, None]


def test_an_asked_part_number_strips_the_year_off_the_facts() -> None:
    """Справку зовут по имени франшизы, и год она называет ПЕРВОЙ картины, а не второй."""
    ask = _Facts(Origin(title="Cars", year=2006, name="Тачки", guessed=True))

    about = _second_origin(ask, "тачки", False, 2, 1.5)

    assert about == Origin(title="Cars", year=None, name="Тачки", guessed=True)


def test_a_silent_answer_without_a_hint_is_not_asked_twice() -> None:
    """Типа не называли - переспрашивать нечем, второго вопроса к справке не бывает."""
    ask = _Facts(Origin())

    assert _second_origin(ask, "дедвуд", None, None, 1.5) == Origin()
    assert len(ask.asked) == 1
