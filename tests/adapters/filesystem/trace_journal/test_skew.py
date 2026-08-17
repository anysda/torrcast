"""Схема ``warm/skew``: уложенный кусок разошёлся с границей сетки."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.skew import skew
from torrcast.domain.trace_sources import PACKED, WARMED


def test_the_offset_is_counted_in_the_record_and_not_left_to_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Разница считается здесь и с тем же знаком: назад - отрицательная.

    Дефект укладки мимо сетки жил незамеченным, потому что выглядел здоровым выборочно.
    Пересчитывай разницу читатель - и первая же ошибка в знаке снова спрятала бы промах.
    """
    seen = caught(monkeypatch)

    skew(slot=359, want=4909.9167, got=4895.1234, hole=True)

    assert seen == [
        (
            "warm",
            "skew",
            {
                "slot": 359,
                "want": 4909.917,
                "got": 4895.123,
                "off": round(4895.1234 - 4909.9167, 3),
                "hole": True,
                "src": WARMED,
            },
        )
    ]
    assert seen[0][2]["off"] < 0, "кусок начался раньше границы - разница отрицательная"


def test_the_producer_of_the_piece_can_be_named_even_though_the_event_is_about_laying_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сверяется пока прогретое, но событие про УКЛАДКУ: по полю видно, чьё производство."""
    seen = caught(monkeypatch)

    skew(slot=1, want=10.0, got=10.0, hole=False, src=PACKED)

    assert seen[0][2]["src"] == PACKED
