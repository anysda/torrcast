"""Зеркало первого круга с именами узнанной картины: текст зрителя и её имена разом."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests.usecases.discover.world import Indexer, row
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
