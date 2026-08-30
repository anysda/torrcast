"""Схема ``play/refetch``: перезабор куска посреди показа и чем он кончился."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.refetch import refetch


def test_a_refetch_carries_the_place_the_count_and_its_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Место, номер попытки и исход: по ним замер и считает заходы внутри терпения."""
    seen = caught(monkeypatch)

    refetch(pos=1234.56, tries=2, ok=False, why="упал: приёмника нет в сети")

    assert seen == [
        (
            "play",
            "refetch",
            {"pos": 1234.6, "tries": 2, "ok": False, "why": "упал: приёмника нет в сети"},
        )
    ]


def test_an_outcome_stands_in_its_own_field_and_not_in_an_empty_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Ушедший перезабор назван ``ok``, а не пустой причиной.

    Пустая причина без отдельного поля значила бы и «перезабор ушёл», и «исход не назвали»,
    а это разные новости: вторую замер обязан уметь отличить от первой.
    """
    seen = caught(monkeypatch)

    refetch(pos=0.0, tries=1, ok=True)

    assert seen[0][2]["ok"] is True
    assert seen[0][2]["why"] == "", "причины у удавшегося перезабора нет, и поле есть"
