"""Круг карточки помнит, ответил ли каталог целиком на каждую спрошенную строку."""

from __future__ import annotations

import json

import pytest

from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.discover.told_circle import ToldCircle
from web.heard_circle import HeardCircle


def test_heard_circle_is_whole_only_when_every_asked_line_was() -> None:
    """Одна строка из трёх ответила урезанным каталогом - картина могла лежать там."""
    full, cut = NothingFoundError("пусто"), NothingFoundError("пусто")
    full.whole = True
    answers = {"a": full, "b": cut}

    def circle(query: str) -> list[object]:
        raise answers[query]

    heard = HeardCircle(circle)  # type: ignore[arg-type]
    marks = [heard.whole]  # nothing asked, nothing proven
    for query in ("a", "b"):
        with pytest.raises(NothingFoundError):
            heard(query)
        marks.append(heard.whole)
    assert marks == [False, True, False]


def test_heard_circle_reads_the_mark_the_plans_carry() -> None:
    plans = ToldCircle([], [])
    plans.whole = True
    heard = HeardCircle(lambda query: plans)
    assert heard("a") is plans
    assert heard.whole


def test_the_refusal_carries_the_mark_of_the_circle() -> None:
    plans = ToldCircle([], [])
    plans.whole = True
    heard = HeardCircle(lambda query: plans)
    heard("a")
    assert json.loads(heard.refusal(None).body) == {"error": "not_found", "whole": True}
    said = json.loads(heard.refusal(TorrcastError("индексеры недоступны")).body)
    assert said == {
        "error": "search_refused",
        "reason": {"key": "web.search.failed", "values": {}},
        "whole": False,
    }
