"""Схема ``play/segment``: кусок, его вес, время отдачи и производитель."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.segment import segment
from torrcast.domain.trace_sources import PACKED


def test_the_source_stands_in_every_record_and_not_only_on_the_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Источник куска - поле каждой записи: по одним переходам показ не читается.

    Живая упаковка и прогрев - разные производители, и разойдись у них решение о
    кодировании, декодер приёмника переинициализируется прямо на стыке. Стыки считает
    разбор недели, а считать ему нечего, если источник назван только на переходах.
    """
    seen = caught(monkeypatch)

    segment(slot=7, mb=3.4567, sent=0.12345, wait=0.6789, src=PACKED)

    assert seen == [
        (
            "play",
            "segment",
            {"slot": 7, "mb": 3.46, "sent": 0.123, "wait": 0.679, "src": PACKED},
        )
    ]
