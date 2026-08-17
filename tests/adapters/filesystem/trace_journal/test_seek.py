"""Схема ``play/seek``: перемотка и время до КАРТИНКИ, а не до слова ``PLAYING``."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.seek import seek


def test_a_seek_that_ended_with_a_picture_carries_the_wait_and_no_excuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ожидание меряется сотыми: замер разводил 3.8 с и 11.9 с, и округление тут значимо."""
    seen = caught(monkeypatch)

    seek(frm=1891.44, to=600.06, wait=6.0449)

    assert seen == [("play", "seek", {"frm": 1891.4, "to": 600.1, "wait": 6.04})]


def test_a_seek_that_ended_with_nothing_is_closed_by_a_record_and_not_by_silence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Картинки не случилось - в ленте пустое ожидание и причина, а не отсутствие строки.

    Молчи запись о таких перемотках - и «нет строки в ленте» пришлось бы читать как
    «перемотки не было», а она была и кончилась ничем: это и есть худший исход, ради
    которого метрику заводили.
    """
    seen = caught(monkeypatch)

    seek(frm=10.0, to=900.0, wait=None, why="сессия оборвалась")

    assert seen == [
        ("play", "seek", {"frm": 10.0, "to": 900.0, "wait": None, "why": "сессия оборвалась"})
    ]


def test_an_empty_reason_does_not_get_a_field_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Причина ставится только тогда, когда её есть чем назвать: пустых полей в ленте нет."""
    seen = caught(monkeypatch)

    seek(frm=0.0, to=10.0, wait=1.0)

    assert "why" not in seen[0][2]
