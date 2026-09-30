"""Checks how long a circle waits, and for whom: its core left unsent, or down."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.prowlarr import circle_wait as circle_wait_module
from torrcast.adapters.prowlarr.circle_wait import circle_wait
from torrcast.adapters.prowlarr.down_book import DownBook
from torrcast.adapters.prowlarr.spawn_ask import _Ask
from torrcast.domain.is_down import DOWN_AFTER


def _waited(asked: list[_Ask], names: bool = True, **kwargs: Any) -> tuple[list[_Ask], float]:
    began = time.monotonic()
    core = circle_wait(asked, names=names, began=began, slack=0.0, **kwargs)
    return core, time.monotonic() - began


@pytest.mark.machine
def test_a_circle_without_a_core_waits_every_one() -> None:
    yts = _Ask("YTS", 0.3)
    core, elapsed = _waited([yts])
    assert core == [yts]
    assert elapsed >= 0.3, f"waited {elapsed:.2f} s for the only one asked"


@pytest.mark.machine
def test_an_unsent_core_holds_the_rest_its_budget_and_no_longer() -> None:
    yts = _Ask("YTS", 5.0)
    core, elapsed = _waited([yts], unsent=[("RuTor", 0.2)])
    assert core == [], "the one left is not the core: it comes late"
    assert 0.2 <= elapsed < 1.0, f"waited {elapsed:.2f} s instead of the unsent budget"


@pytest.mark.machine
def test_the_rest_that_answers_within_the_hold_ends_it() -> None:
    yts = _Ask("YTS", 5.0)
    threading.Timer(0.1, yts.done.set).start()
    _core, elapsed = _waited([yts], unsent=[("RuTor", 0.2)])
    assert yts.done.is_set()
    assert elapsed < 0.2, f"waited {elapsed:.2f} s after the last answer"


@pytest.mark.machine
def test_an_unsent_quorum_does_not_hold_a_circle_of_names() -> None:
    rutor, yts = _Ask("RuTor", 5.0), _Ask("YTS", 5.0)
    threading.Timer(0.1, rutor.done.set).start()
    core, elapsed = _waited([rutor, yts], unsent=[("Knaben", 0.5)])
    assert core == [rutor] and not yts.done.is_set(), "YTS only adds rows: it comes late"
    assert elapsed < 0.4, f"waited {elapsed:.2f} s for a quorum the names never wait"


def test_the_quorum_holds_only_the_viewers_text() -> None:
    knaben, rutor = _Ask("Knaben", 0.1), _Ask("RuTor", 0.1)
    assert circle_wait([knaben, rutor], names=True, began=0.0, slack=0.0) == [rutor]
    assert circle_wait([knaben, rutor], names=False, began=0.0, slack=0.0) == [knaben, rutor]


def _down(tmp_path: Path, *names: str) -> DownBook:
    book = DownBook(lambda: tmp_path / "down.json")
    for name in names:
        for _ in range(DOWN_AFTER):
            book.hear(name, answered=False)
    return book


@pytest.mark.machine
def test_a_down_core_does_not_hold_the_circle(tmp_path: Path) -> None:
    knaben, rutor = _Ask("Knaben", 5.0), _Ask("RuTor", 5.0)
    threading.Timer(0.1, rutor.done.set).start()
    core, elapsed = _waited([knaben, rutor], book=_down(tmp_path, "Knaben"), names=False)
    assert core == [rutor], "Knaben is asked, not waited: its rows come late if at all"
    assert elapsed < 1.0, f"waited {elapsed:.2f} s for a source that is down"


@pytest.mark.machine
def test_a_circle_of_names_with_its_only_core_down_waits_the_others(tmp_path: Path) -> None:
    """The year circle: Knaben is no core there, and a down JacRed held it to its 5 s zero."""
    jacred, knaben, yts = _Ask("JacRed", 5.0), _Ask("Knaben", 5.0), _Ask("YTS", 5.0)
    threading.Timer(0.1, knaben.done.set).start()
    threading.Timer(0.2, yts.done.set).start()
    core, elapsed = _waited([jacred, knaben, yts], book=_down(tmp_path, "JacRed"))
    assert core == [knaben, yts], "JacRed is asked, not waited: its rows come late if at all"
    assert elapsed < 1.0, f"waited {elapsed:.2f} s for a source that is down"


def test_a_core_all_down_is_waited_as_before(tmp_path: Path) -> None:
    knaben, rutor = _Ask("Knaben", 0.0), _Ask("RuTor", 0.0)
    book = _down(tmp_path, "Knaben", "RuTor")
    core = circle_wait([knaben, rutor], names=False, began=0.0, slack=0.0, book=book)
    assert core == [knaben, rutor]


def test_a_core_given_up_after_the_whole_wait_is_told_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its thread may live 45 s more: a restart before that would never tell the book."""
    monkeypatch.setattr(circle_wait_module, "IN_TIME", 0.0)
    book = DownBook(lambda: tmp_path / "down.json")
    for _ in range(DOWN_AFTER):
        circle_wait([_Ask("Knaben", 0.0)], names=False, began=0.0, slack=0.0, book=book)
    assert book.down() == {"Knaben"}


def test_a_short_wait_tells_nothing(tmp_path: Path) -> None:
    """A second circle capped to a second gave up on Knaben too early to call it silent."""
    book = DownBook(lambda: tmp_path / "down.json")
    for _ in range(DOWN_AFTER):
        circle_wait([_Ask("Knaben", 1.0)], names=False, began=0.0, slack=0.0, book=book)
    assert book.down() == frozenset()


@pytest.mark.machine
def test_a_lone_core_of_names_ends_with_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The year circle: JacRed's names wait two seconds behind its text in Prowlarr."""
    monkeypatch.setattr(circle_wait_module, "IN_TIME", 0.0)
    book = DownBook(lambda: tmp_path / "down.json")
    for _ in range(DOWN_AFTER):
        jacred, knaben, yts = _Ask("JacRed", 5.0), _Ask("Knaben", 5.0), _Ask("YTS", 5.0)
        threading.Timer(0.1, knaben.done.set).start()
        threading.Timer(0.2, yts.done.set).start()
        core, elapsed = _waited([jacred, knaben, yts], book=book)
        assert core == [knaben, yts], "JacRed comes late: the others ended the circle"
        assert elapsed < 1.0, f"waited {elapsed:.2f} s for JacRed after the others answered"
    assert book.down() == frozenset(), "a circle the others ended does not tell JacRed silent"


@pytest.mark.machine
def test_a_lone_core_of_names_that_answers_first_ends_the_circle() -> None:
    jacred, yts = _Ask("JacRed", 5.0), _Ask("YTS", 5.0)
    threading.Timer(0.1, jacred.done.set).start()
    core, elapsed = _waited([jacred, yts])
    assert core == [jacred] and not yts.done.is_set(), "YTS only adds rows: it comes late"
    assert elapsed < 1.0, f"waited {elapsed:.2f} s for YTS after JacRed answered"


def test_a_lone_core_of_the_viewers_text_is_waited_alone() -> None:
    jacred, yts = _Ask("JacRed", 0.0), _Ask("YTS", 0.0)
    yts.done.set()
    assert circle_wait([jacred, yts], names=False, began=0.0, slack=0.0) == [jacred]


def _answer(ask: _Ask, after: float, rows: int) -> None:
    def said() -> None:
        ask.rows = [object()] * rows  # type: ignore[list-item]
        ask.done.set()

    threading.Timer(after, said).start()


@pytest.mark.machine
def test_a_slow_quorum_does_not_hold_rows_the_others_brought(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Knaben's own answer took 5-8 s where RuTor and JacRed were in within a second."""
    monkeypatch.setattr(circle_wait_module, "IN_TIME", 0.0)
    book = DownBook(lambda: tmp_path / "down.json")
    for _ in range(DOWN_AFTER):
        knaben, rutor = _Ask("Knaben", 5.0), _Ask("RuTor", 5.0)
        _answer(rutor, 0.1, rows=2)
        core, elapsed = _waited([knaben, rutor], names=False, book=book, grace=0.2)
        assert core == [rutor], "Knaben comes late, as one the circle did not wait"
        assert 0.3 <= elapsed < 0.8, f"waited {elapsed:.2f} s, not the grace past RuTor"
    assert book.down() == frozenset(), "a quorum cut by the grace is not told silent"


@pytest.mark.machine
def test_an_empty_pool_waits_the_quorum_whole() -> None:
    """Without the quorum an empty list proves nothing: no film or no catalogue."""
    knaben, rutor = _Ask("Knaben", 5.0), _Ask("RuTor", 5.0)
    _answer(rutor, 0.1, rows=0)
    _answer(knaben, 0.6, rows=1)
    core, elapsed = _waited([knaben, rutor], names=False, grace=0.2)
    assert core == [knaben, rutor] and knaben.done.is_set()
    assert elapsed >= 0.6, f"gave up on the quorum after {elapsed:.2f} s with nothing to show"
