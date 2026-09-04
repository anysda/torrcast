"""Схема ``play/reload``: повтор LOAD посреди показа, его исход и код прежней смерти."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.reload import reload


def test_a_retry_carries_the_place_the_count_and_the_code_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Место, номер попытки и код: по ним и видно, чинился показ или добивался."""
    seen = caught(monkeypatch)

    reload(pos=1234.56, tries=2, ok=True, error=905)

    assert seen == [
        ("play", "reload", {"pos": 1234.6, "tries": 2, "ok": True, "why": "", "error": 905})
    ]


def test_a_retry_without_a_code_says_so_instead_of_pretending_there_was_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Кода не назвали - в записи стоит пустота, а не чужой код прошлой загрузки.

    Приписать повтору код предыдущего отказа значит соврать в единственном поле, ради
    которого запись и читают.
    """
    seen = caught(monkeypatch)

    reload(pos=0.0, tries=1, ok=True)

    assert seen[0][2]["error"] is None


def test_the_outcome_of_the_retry_stands_apart_from_the_code_that_caused_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 ``ok`` - про повтор, ``error`` - про смерть, которая его вызвала.

    Слить их в одно поле нельзя: код прежней сессии стоит и у ушедшего повтора, и у
    легшего, а ``error: null`` не значит ни «удалось», ни «не удалось» вовсе. Ровно так
    замер 30-08-2026 и прочитал чёрный экран удачей.
    """
    seen = caught(monkeypatch)

    reload(pos=0.0, tries=1, ok=False, why="упал: приёмника нет в сети", error=905)

    assert seen[0][2]["ok"] is False
    assert seen[0][2]["why"] == "упал: приёмника нет в сети"
    assert seen[0][2]["error"] == 905, "повод повтора остаётся на месте и у отказа"


def test_a_retry_that_went_out_leaves_an_empty_reason_next_to_its_own_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустая причина без отдельного ``ok`` значила бы и «ушёл», и «исход не назвали»."""
    seen = caught(monkeypatch)

    reload(pos=0.0, tries=1, ok=True)

    assert seen[0][2]["ok"] is True
    assert seen[0][2]["why"] == "", "причины у ушедшего повтора нет, и поле есть"
