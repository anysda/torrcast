"""Схема ``warm/ready`` и ``warm/stall``: доля прогретого считается при записи."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.warmth import warmth


def test_the_share_is_counted_here_so_the_reader_of_the_tape_does_not_do_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Доля стоит в записи готовой: пересчитывай её читатель - расходились бы округления."""
    seen = caught(monkeypatch)

    warmth("ready", secs=3600.4, dur=7200.6, size=13_300_000_000)

    assert seen == [
        (
            "warm",
            "ready",
            {"secs": 3600, "dur": 7201, "share": 0.5, "size": 13_300_000_000, "why": ""},
        )
    ]


def test_a_film_without_a_length_gives_a_zero_share_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Длины ещё не знают - доля ноль: запись про прогрев не имеет права уронить прогрев."""
    seen = caught(monkeypatch)

    warmth("stall", secs=10.0, dur=0.0, size=0, why="источник молчит")

    assert seen[0][2]["share"] == 0.0
    assert seen[0][2]["why"] == "источник молчит"
