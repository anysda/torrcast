"""Полнота круга индексеров: «раздач нет» правдиво, только когда ответил каждый."""

from __future__ import annotations

import time

import pytest

from tests.adapters.prowlarr.test_prowlarr import _ago, _swarm, _swarm_of
from torrcast.adapters.prowlarr.down_book import DOWN_BOOK
from torrcast.domain.is_down import DOWN_AFTER
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


@pytest.mark.machine
def test_a_quorum_the_grace_let_go_leaves_the_circle_part_but_not_silent() -> None:
    """The memory must not keep a circle without the quorum's rows as the catalogue."""
    client = _swarm(rows=2, hold={1})
    try:
        began = time.monotonic()
        client.search("матрица")
        assert time.monotonic() - began < 3.0, "the others brought rows: the grace ends it"
        assert client.waiting() == ("Knaben",)
        assert (client.heard(), client.silent) == (False, ())
    finally:
        _swarm_of(client).gate.set()
        client.late(wait=5.0)


def _settled(want: frozenset[str]) -> frozenset[str]:
    """The threads tell the book right after their flag: give them a moment."""
    deadline = time.monotonic() + 2.0
    while (down := DOWN_BOOK.down()) != want and time.monotonic() < deadline:
        time.sleep(0.01)
    return down


def test_a_source_silent_in_a_row_leaves_the_next_circles_heard() -> None:
    """The mark ``part`` held for good: nothing but a whole circle took it off (TC-1391)."""
    for _ in range(DOWN_AFTER - 1):
        client = _swarm(rows=2, mute=1)
        client.search("матрица")
        assert not client.heard(), "one silence is not a verdict: the circle is part"
    _swarm(rows=2, mute=1).search("матрица")
    assert _settled(frozenset({"Knaben"})) == {"Knaben"}
    client = _swarm(rows=2, mute=1)
    client.search("матрица")
    assert client.heard() and not client.whole(), "heard without the down one, never whole"
    assert client.gone()[0] == ("Knaben",), "the person is still told who kept silent"


def test_a_down_source_that_answers_is_back() -> None:
    for _ in range(DOWN_AFTER):
        _swarm(rows=2, mute=1).search("матрица")
    assert _settled(frozenset({"Knaben"})) == {"Knaben"}
    _swarm(rows=2).search("матрица")
    assert _settled(frozenset()) == frozenset()
    client = _swarm(rows=2, mute=1)
    client.search("матрица")
    assert not client.heard(), "back to unknown: its next silence makes the circle part again"
