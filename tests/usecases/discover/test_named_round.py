"""Зеркало первого круга с именами узнанной картины: текст зрителя и её имена разом."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from tests.usecases.discover.world import Indexer, row
from torrcast.adapters.prowlarr.warmup import WARMUP, warmup
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.infra_error import InfraError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._search_state import _configure_recognize
from torrcast.usecases.discover.named_round import NamedRound
from torrcast.usecases.discover.told_indexer import ToldIndexer

_INTERSTELLAR = MapPicture("Интерстеллар", 2014, False, "Interstellar", 2_605_028)
_ROW = row("Интерстеллар / Interstellar (2014) BDRip 1080p", "a")


class _Broken(Indexer):
    def search(self, query: str) -> list[RawResult]:
        raise InfraError("Prowlarr не отвечает")


def _round(
    typed: str, known: MapPicture | None, spawned: list[Indexer]
) -> tuple[NamedRound, list[RawResult], list[RawResult]]:
    _configure_recognize(lambda _query, _wait: known)
    answers = {"интерстеллар 2014": [_ROW], "interstellar 2014": [_ROW]}

    def spawn() -> Indexer:
        spawned.append(Indexer(answers=answers))
        return spawned[-1]

    source = spawn()
    first = NamedRound(source)
    raw, named = first.ask(ToldIndexer(source), spawn, None, typed, typed)
    return first, raw, named


def test_the_names_and_year_of_the_picture_are_asked_beside_the_typed_text() -> None:
    spawned: list[Indexer] = []
    first, raw, named = _round("Интерстелар", _INTERSTELLAR, spawned)

    assert sorted(query for one in spawned for query in one.asked) == [
        "Interstellar 2014",
        "Интерстелар",
        "Интерстеллар 2014",
    ]
    assert (raw, len(named), first.known) == ([], 2, _INTERSTELLAR)
    assert len(first.named_inflight()) == 0, "подделка не держит строк в пути"


def test_an_unrecognized_text_is_the_plain_search_of_it() -> None:
    spawned: list[Indexer] = []
    _, _, named = _round("ывапрол", None, spawned)
    assert ([one.asked for one in spawned], named) == ([["ывапрол"]], [])


def test_a_series_is_asked_without_a_year_and_the_typed_name_is_not_asked_twice() -> None:
    spawned: list[Indexer] = []
    series = MapPicture("Наруто", 2002, True, "Naruto", 174_119)
    _round("наруто", series, spawned)
    assert [one.asked for one in spawned] == [["наруто"], ["Naruto"]]


def test_a_broken_name_round_does_not_break_the_search() -> None:
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    source = Indexer(answers={"интерстелар": [_ROW]})
    raw, named = NamedRound(source).ask(
        ToldIndexer(source), _Broken, None, "Интерстелар", "Интерстелар"
    )
    assert (raw, named) == ([_ROW], [])


def test_a_map_built_a_moment_late_still_names_a_text_nobody_answered() -> None:
    known: list[MapPicture | None] = [None, _INTERSTELLAR]
    _configure_recognize(lambda _query, _wait: known.pop(0))
    spawned: list[Indexer] = []

    def spawn() -> Indexer:
        spawned.append(Indexer(answers={"интерстеллар 2014": [_ROW], "interstellar 2014": [_ROW]}))
        return spawned[-1]

    source = spawn()
    first = NamedRound(source)
    raw, named = first.ask(ToldIndexer(source), spawn, None, "Интерстелар", "Интерстелар")
    assert (raw, len(named), len(spawned)) == ([], 2, 3)


class _Joint(Indexer):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.joints: list[str] = []

    def beside(self, joint: str) -> None:
        self.joints.append(joint)


def test_one_client_of_the_names_carries_them_all_to_the_joined_indexer() -> None:
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    spawned: list[_Joint] = []

    def spawn() -> _Joint:
        spawned.append(_Joint(answers={"интерстеллар 2014": [_ROW]}))
        return spawned[-1]

    source = spawn()
    NamedRound(source).ask(ToldIndexer(source), spawn, None, "Интерстелар", "Интерстелар")
    assert [(one.asked, one.joints) for one in spawned] == [
        (["Интерстелар"], []),
        (["Интерстеллар 2014"], ["Интерстеллар 2014 | Interstellar 2014"]),
        (["Interstellar 2014"], [""]),
    ]


class _Along(_Joint):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.carried: list[str] = []

    def along(self, names: str) -> None:
        self.carried.append(names)


@pytest.mark.parametrize("built", [True, False])
def test_the_viewers_text_carries_the_names_to_the_joined_indexer_on_a_built_map(
    built: bool,
) -> None:
    # Asked apart, JacRed's names began two seconds after its text began (Prowlarr's pace).
    _configure_recognize(lambda _query, wait: _INTERSTELLAR if built or wait else None)
    spawned: list[_Along] = []

    def spawn() -> _Along:
        spawned.append(_Along(answers={"интерстеллар 2014": [_ROW]}))
        return spawned[-1]

    source = spawn()
    NamedRound(source).ask(ToldIndexer(source), spawn, None, "Интерстелар", "Интерстелар")
    joined = "Интерстеллар 2014 | Interstellar 2014"
    assert source.carried == ([joined] if built else [])
    assert [one.joints for one in spawned[1:]] == ([[""], [""]] if built else [[joined], [""]])
    assert sorted(query for one in spawned for query in one.asked) == [
        "Interstellar 2014",
        "Интерстелар",
        "Интерстеллар 2014",
    ], "the names still go to every other indexer by their own clients"


class _Held(Indexer):
    def __init__(self, gate: threading.Event) -> None:
        super().__init__()
        self.gate = gate

    def search(self, query: str) -> list[RawResult]:
        self.gate.wait(2.0)
        return []


@pytest.mark.machine
def test_the_viewers_text_is_known_while_the_names_are_still_asked() -> None:
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    gate = threading.Event()
    seen = threading.Event()
    source = Indexer(answers={"интерстелар": [_ROW]})
    first = NamedRound(source)
    typed_in: list[bool] = []

    def watch(_client: object) -> None:
        def wait() -> None:
            typed_in.append(first.typed.wait(1.0))
            seen.set()

        threading.Thread(target=wait).start()

    asked = threading.Thread(
        target=first.ask,
        args=(ToldIndexer(source), lambda: _Held(gate), watch, "Интерстелар", "Интерстелар"),
    )
    asked.start()
    seen.wait(1.5)
    gate.set()
    asked.join()
    assert typed_in == [True], "the viewer's text answered, and the round kept it to itself"
    assert first.ahead, "the names were still asked, and the round did not say so"


class _Last(Indexer):
    def __init__(self, names: threading.Event) -> None:
        super().__init__(answers={"интерстелар": [_ROW]})
        self.names = names

    def search(self, query: str) -> list[RawResult]:
        self.names.wait(2.0)
        time.sleep(0.1)
        return super().search(query)


class _Quick(Indexer):
    def __init__(self, names: threading.Event) -> None:
        super().__init__()
        self.names = names

    def search(self, query: str) -> list[RawResult]:
        self.names.set()
        return []


@pytest.mark.machine
def test_a_viewers_text_answered_last_is_not_ahead_of_the_names() -> None:
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    names = threading.Event()
    source = _Last(names)
    first = NamedRound(source)
    first.ask(ToldIndexer(source), lambda: _Quick(names), None, "Интерстелар", "Интерстелар")
    assert first.typed.is_set()
    assert not first.ahead, "the names were in, and the round still called the text ahead"


class _Host(Indexer):
    """Индексер за Prowlarr: запрос уходит к хосту не сразу, и хост помнит, чей был первым."""

    def __init__(self, arrived: list[str], delay: float) -> None:
        super().__init__(answers={"интерстеллар 2014": [_ROW], "interstellar 2014": [_ROW]})
        self._arrived, self._delay, self._sent = arrived, delay, threading.Event()

    def sent(self, wait: float) -> bool:
        return self._sent.wait(wait)

    def search(self, query: str) -> list[RawResult]:
        time.sleep(self._delay)
        self._arrived.append(query)
        self._sent.set()
        return super().search(query)


def test_the_typed_text_reaches_the_host_before_the_picture_names() -> None:
    # Prowlarr paces one host two seconds apart: whoever comes second waits. The early card
    # counts the viewer's text, so the text goes first even when its client starts slower.
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    arrived: list[str] = []
    source = _Host(arrived, 0.2)
    NamedRound(source).ask(
        ToldIndexer(source), lambda: _Host(arrived, 0.0), None, "Интерстелар", "Интерстелар"
    )
    assert arrived[0] == "Интерстелар", arrived


class _Marked(Indexer):
    def __init__(self, marks: list[bool]) -> None:
        super().__init__(answers={"интерстеллар 2014": [_ROW]})
        self.marks = marks

    def search(self, query: str) -> list[RawResult]:
        self.marks.append(WARMUP.get())
        return super().search(query)


def test_a_warmups_mark_reaches_every_ask_of_the_round() -> None:
    # The round asks from its own pool; a warmup's circle there must still give way to a viewer.
    _configure_recognize(lambda _query, _wait: _INTERSTELLAR)
    marks: list[bool] = []
    source = _Marked(marks)
    with warmup():
        NamedRound(source).ask(
            ToldIndexer(source), lambda: _Marked(marks), None, "Интерстелар", "Интерстелар"
        )
    assert marks == [True, True, True], marks
