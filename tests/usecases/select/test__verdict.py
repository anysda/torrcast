"""Зеркало приговоров отбора: что попадает в след и чем осечка роя отличается от отказа."""

from __future__ import annotations

import pytest

from tests.usecases.select.world import release
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._verdict import (
    _did_not_answer,
    _silenced,
    _turned_down,
    _waiting_note,
)


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русские приговоры отбора и русская осечка терпения."""


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
    waited = SwarmError("пиров нет за 30 с", waited=30.0)

    assert _waiting_note(_prep(failure=waited), "пиров нет за 30 с") == "не дождались за 30 с"


@pytest.mark.parametrize(
    ("language", "expected"),
    [(RU, "не дождались за 30 с"), (EN, "gave up after 30s")],
    ids=["ru", "en"],
)
def test_the_seconds_we_waited_come_from_the_refusal_not_from_its_wording(
    language: str, expected: str
) -> None:
    """🔴 Число секунд приезжает полем отказа, и приговор один и тот же на обоих языках.

    Разбор готовой жалобы регуляркой ``за (\\d+) с`` держался ровно до перевода кластера
    :mod:`torrcast.domain.catalogs.torrserver`: английская жалоба мимо русских слов, и
    приговор молча сваливался с «не дождались за 30 с» на «не дождались». Мера двусторонняя
    нарочно: прибор, спрошенный на одном языке, на такую поломку отвечает зелёным.

    Жалоба тут нарочно английская при ОБОИХ языках зрителя - так её и пишет боевой
    :class:`~torrcast.adapters.torrserver.torr_server.TorrServer`, когда язык продукта
    английский: приговор не вправе зависеть от того, какими словами написан отказ.
    """
    _choose_tongue(language)
    refusal = SwarmError("swarm is empty - not one peer in 30 s", waited=30.0)

    assert _waiting_note(_prep(failure=refusal), str(refusal)) == expected


def test_a_silence_that_never_counted_seconds_names_patience_without_a_number() -> None:
    """Сколько ждали, отсюда не видно - терпение называется, а число не выдумывается.

    Так приезжает молчание роя, замеченное паспортом
    (:func:`torrcast.adapters.stream_probe.run_ffprobe.run_ffprobe`), и так же выглядит
    фаза, не уложившаяся в бюджет: отказа нет вовсе.
    """
    assert _waiting_note(_prep(failure=SwarmError("рой молчит")), "рой молчит") == "не дождались"
    assert _waiting_note(_prep(), "фаза «метаданные» не уложилась в бюджет") == "не дождались"


def test_a_known_release_keeps_its_own_reason() -> None:
    """Про раздачу известно всё - её собственная причина и остаётся в строке."""
    prep = _prep(failure=NotFoundError("серии нет"))

    assert _waiting_note(prep, "нужной серии нет за 30 с") == "нужной серии нет за 30 с"
