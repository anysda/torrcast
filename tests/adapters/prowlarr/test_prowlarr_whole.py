"""Полнота круга индексеров: «раздач нет» правдиво, только когда ответил каждый."""

from __future__ import annotations

import pytest

from tests.adapters.prowlarr.test_prowlarr import _ago, _swarm, _swarm_of
from torrcast.domain.not_found_error import NotFoundError


def test_an_honest_zero_is_whole() -> None:
    client = _swarm(rows=0)
    with pytest.raises(NotFoundError):
        client.search("матрица")
    assert client.whole()


def test_a_circle_with_rows_is_whole_when_everyone_answered() -> None:
    client = _swarm()
    client.search("матрица")
    assert client.whole()


@pytest.mark.parametrize(
    "broken",
    [
        {"refuses": {1}},  # отказ за «200 []»
        {"mute": 1},  # молчит до бюджета
        {"yts": True, "blocked": {4: _ago(300)}},  # в бане
    ],
    ids=["refused", "silent", "banned"],
)
def test_one_missing_indexer_makes_the_emptiness_unproven(broken: dict[str, object]) -> None:
    """Картина могла лежать как раз у того, кто не ответил: такая пустота не приговор."""
    client = _swarm(rows=0, **broken)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        client.search("матрица")
    assert not client.whole()


def test_a_client_that_never_asked_proved_nothing() -> None:
    assert not _swarm().whole()


@pytest.mark.parametrize(
    ("broken", "fell"),
    [
        ({}, ((), (), ())),
        ({"refuses": {1}}, ((), (), ("Knaben",))),
        ({"mute": 1}, (("Knaben",), (), ())),
        ({"yts": True, "blocked": {4: _ago(300)}}, ((), ("YTS",), ())),
    ],
    ids=["whole", "refused", "silent", "banned"],
)
def test_the_client_names_who_fell_out(broken: dict[str, object], fell: object) -> None:
    """A cut empty circle owes the person its missing names, each by what befell it.

    One that refused behind an empty page is not silent: it answered, with a refusal.
    """
    client = _swarm(rows=0, **broken)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        client.search("матрица")
    assert client.gone() == fell


@pytest.mark.parametrize(
    ("broken", "heard"),
    [
        ({}, True),
        ({"refuses": {1}}, False),
        ({"mute": 1}, False),
        ({"yts": True, "blocked": {4: _ago(300)}}, True),
    ],
    ids=["whole", "refused", "silent", "banned"],
)
def test_only_one_prowlarr_took_away_leaves_the_circle_heard(
    broken: dict[str, object], heard: bool
) -> None:
    """Prowlarr's banned one was not asked; everyone asked answering is all a circle can hear."""
    client = _swarm(rows=0, **broken)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        client.search("матрица")
    assert client.heard() is heard


@pytest.mark.machine
def test_a_tail_the_circle_went_on_without_leaves_it_heard_but_not_whole() -> None:
    """The screen still waits for the late one; the memory keeps what the circle waited for."""
    client = _swarm(rows=2, hold={3})
    try:
        client.search("Naruto [TV]")
        assert client.waiting() == ("Nyaa.si",)
        assert (client.whole(), client.heard()) == (False, True)
    finally:
        _swarm_of(client).gate.set()
        client.late(wait=5.0)
