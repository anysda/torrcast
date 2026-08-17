"""Схема ``play/dark``: показ погас, и видел ли зритель до этого хоть один кадр."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.dark import dark


def test_the_darkness_that_followed_a_picture_is_not_the_same_beast_as_a_show_that_never_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``shown`` разводит две аварии, которые нельзя считать одной.

    Погасший показ человек успел посмотреть, а показ, не давший ни кадра, - это «включил
    и не включилось», самая дорогая беда лестницы цели. Слейся они в одну запись - и
    недельный разбор перестал бы отличать досадную от главной.
    """
    seen = caught(monkeypatch)

    dark(pos=1272.44, why="приёмник молчит", shown=False)

    assert seen == [("play", "dark", {"pos": 1272.4, "why": "приёмник молчит", "shown": False})]


def test_a_show_that_was_watched_before_it_died_says_so_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Умолчание - «зритель смотрел»: обычный конец показа это именно он."""
    seen = caught(monkeypatch)

    dark(pos=0.0, why="обрыв источника")

    assert seen[0][2]["shown"] is True
