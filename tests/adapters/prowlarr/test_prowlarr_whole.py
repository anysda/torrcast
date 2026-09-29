"""Полнота круга индексеров: «раздач нет» правдиво, только когда ответил каждый."""

from __future__ import annotations

import pytest

from tests.adapters.prowlarr.test_prowlarr import _ago, _swarm
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
    ("broken", "silent", "banned"),
    [
        ({}, 0, 0),
        ({"refuses": {1}}, 1, 0),
        ({"mute": 1}, 1, 0),
        ({"yts": True, "blocked": {4: _ago(300)}}, 0, 1),
    ],
    ids=["whole", "refused", "silent", "banned"],
)
def test_the_client_names_who_fell_out(broken: dict[str, object], silent: int, banned: int) -> None:
    """A cut empty circle owes the person its missing names: a silent one is not a banned one."""
    client = _swarm(rows=0, **broken)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        client.search("матрица")
    quiet, taken = client.gone()
    assert (len(quiet), len(taken)) == (silent, banned), (quiet, taken)
    assert not set(quiet) & set(taken)
