"""Зеркало прогрева офлайн-карты: он читает карту сам, фоном, и не держит звавшего."""

from __future__ import annotations

import threading
import time

import pytest

from hass.warm_facts import warm_facts
from torrcast.runtime.facts_wiring import FACTS


def test_warm_facts_reads_the_map_in_a_background_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow_names() -> dict[str, list[object]]:
        calls.append(1)
        started.set()
        release.wait(1.0)
        return {}

    monkeypatch.setattr(FACTS.catalogue, "names", slow_names)
    before = time.monotonic()
    warm_facts()
    # Звавший не ждёт: разбор карты живёт своим потоком, и вызов возвращается тут же.
    assert time.monotonic() - before < 0.1
    assert started.wait(1.0)
    release.set()
    assert calls == [1]
