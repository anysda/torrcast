"""Схема ``play/reload``: повтор LOAD посреди показа и код отказа, если он назван."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.reload import reload


def test_a_retry_carries_the_place_the_count_and_the_code_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Место, номер попытки и код: по ним и видно, чинился показ или добивался."""
    seen = caught(monkeypatch)

    reload(pos=1234.56, tries=2, error=905)

    assert seen == [("play", "reload", {"pos": 1234.6, "tries": 2, "error": 905})]


def test_a_retry_without_a_code_says_so_instead_of_pretending_there_was_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Кода не назвали - в записи стоит пустота, а не чужой код прошлой загрузки.

    Приписать повтору код предыдущего отказа значит соврать в единственном поле, ради
    которого запись и читают.
    """
    seen = caught(monkeypatch)

    reload(pos=0.0, tries=1)

    assert seen[0][2]["error"] is None
