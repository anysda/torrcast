"""Зеркало приговоров отбора: что попадает в след и чем осечка роя отличается от отказа."""

from __future__ import annotations

from tests.usecases.select.world import release
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal import Silent, install
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import (
    _did_not_answer,
    _silenced,
    _turned_down,
    _waiting_note,
)


class _Noted(Silent):
    """Молчащая лента, которая помнит события отбора."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.events.append((phase, event, dict(fields)))


def _prep(failure: TorrcastError | None = None) -> _Prep:
    return _Prep(number=1, release=release(), failure=failure)


def test_a_verdict_is_remembered_and_written_to_the_trace_at_once() -> None:
    """🔴 TC-194. Отказ не может напечататься мимо следа: рождаются они одной строкой."""
    judged: dict[int, str] = {}
    noted = _Noted()
    install(noted)
    try:
        _turned_down(judged, 3, "битрейт выше потолка")
    finally:
        install(Silent())

    assert judged == {3: "битрейт выше потолка"}
    assert noted.events == [("select", "drop", {"release": 3, "why": "битрейт выше потолка"})]


def test_our_own_waiting_is_not_a_verdict_on_the_release() -> None:
    """Осечка роя пишется в след, но приговором раздаче не становится."""
    noted = _Noted()
    install(noted)
    try:
        _did_not_answer(2, "рой молчит")
    finally:
        install(Silent())

    assert noted.events == [("select", "drop", {"release": 2, "why": "рой молчит"})]


def test_a_swarm_that_told_us_nothing_is_a_silence_not_a_sentence() -> None:
    """Про сам релиз мы так ничего и не узнали - это молчание роя."""
    assert _silenced(_prep(failure=SwarmError("рой молчит"))) is True
    assert _silenced(_prep()) is True, "фаза не уложилась в бюджет - тоже неизвестность"


def test_a_release_we_learnt_everything_about_is_not_a_silence() -> None:
    """«Нужной серии тут нет» - про раздачу узнали всё, и терпение ей не добавит ничего."""
    assert _silenced(_prep(failure=NotFoundError("серии нет"))) is False


def test_the_note_names_our_patience_not_an_empty_swarm() -> None:
    """Неизвестный рой пустым не объявляют: строка говорит про наше ожидание."""
    assert _waiting_note(_prep(), "пиров нет за 30 с") == "не дождались за 30 с"


def test_a_known_release_keeps_its_own_reason() -> None:
    """Про раздачу известно всё - её собственная причина и остаётся в строке."""
    prep = _prep(failure=NotFoundError("серии нет"))

    assert _waiting_note(prep, "нужной серии нет за 30 с") == "нужной серии нет за 30 с"
