"""Гонка источников хранит ответы обоих: запас плитки берётся из памяти, а не из сети."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from hass.poster_race import PosterRace
from torrcast.domain.facts.ask import Ask

HERE = Ask("Матрица", 1999, "movie", "The Matrix")
WIKI = "https://upload.wikimedia.org/poster.jpg"
IMDB = "https://m.media-amazon.com/images/M/one._V1_.jpg"


def _answer(pages: list[str], gate: threading.Event | None = None) -> Callable[..., object]:
    def ask(_heard: Callable[..., None]) -> dict[Ask, list[str]]:
        if gate is not None:
            gate.wait(5.0)
        return {HERE: pages}

    return ask


def test_the_spare_holds_both_answers_in_trust_order() -> None:
    race = PosterRace(_answer([WIKI]), _answer([IMDB]))
    assert race.spare(HERE, time.monotonic() + 5.0) == [WIKI, IMDB]


def test_the_spare_waits_for_a_source_still_on_the_wire() -> None:
    gate = threading.Event()
    race = PosterRace(_answer([WIKI], gate), _answer([IMDB]))
    threading.Timer(0.2, gate.set).start()
    assert race.spare(HERE, time.monotonic() + 5.0) == [WIKI, IMDB]


def test_a_broken_source_leaves_only_the_other_answer() -> None:
    def broken(_heard: Callable[..., None]) -> dict[Ask, list[str]]:
        raise OSError("wiki down")

    race = PosterRace(broken, _answer([IMDB]))
    assert race.spare(HERE, time.monotonic() + 5.0) == [IMDB]
    assert race.said([HERE]) == {HERE: [IMDB]}
