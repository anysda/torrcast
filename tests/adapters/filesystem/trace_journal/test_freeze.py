"""Схема ``play/freeze``: потерянная плёнка, запас упаковки и слово приёмника рядом."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.freeze import freeze


def test_the_record_keeps_the_receiver_word_next_to_the_lost_film(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Состояние стоит в записи рядом с потерей: на приставке оно всё это время «играю».

    Без него запись читалась бы как ребуфер, а ребуфера тут не было ни одного: подгруз
    доказан ходом указателя. ``front`` отличает зависание приёмника от ожидания нас.
    """
    seen = caught(monkeypatch)

    freeze(pos=163.87, lost=7.412, secs=8.14, total=12.633, front=201.06, state="PLAYING")

    assert seen == [
        (
            "play",
            "freeze",
            {
                "pos": 163.9,
                "lost": 7.41,
                "secs": 8.1,
                "total": 12.63,
                "front": 201.1,
                "state": "PLAYING",
            },
        )
    ]
