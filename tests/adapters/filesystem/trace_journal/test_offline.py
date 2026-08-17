"""Схема ``play/offline``: источник перестал читаться, и кто это сказал."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.offline import offline


def test_the_record_says_whether_the_source_named_the_trouble_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Упаковка оборвалась» и «служба раздач не отвечает» в показе выглядят одинаково.

    Значат они разное, и в следе это должно быть видно без гадания - отсюда ``asked``:
    правда ли причину назвал сам источник, а не мёртвый прогон упаковки.
    """
    seen = caught(monkeypatch)

    offline("торрент не отвечает", asked=True)

    assert seen == [("play", "offline", {"why": "торрент не отвечает", "asked": True})]


def test_a_guess_is_written_as_a_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Догадка по мёртвому прогону едет в ленту с честной пометкой, а не как ответ службы."""
    seen = caught(monkeypatch)

    offline("упаковка встала")

    assert seen[0][2]["asked"] is False
