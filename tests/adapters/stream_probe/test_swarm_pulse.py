"""Признак жизни потока: пришёл байт - раздача жива; молчание дольше отсрочки - рой пуст."""

from __future__ import annotations

import time
import urllib.request
from typing import Any

import pytest

from torrcast.adapters.stream_probe.swarm_pulse import swarm_pulse


class _Answer:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self, size: int) -> bytes:
        return self.payload[:size]

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _served(payload: bytes, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    asked: list[Any] = []

    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        asked.append(request)
        return _Answer(payload)

    # Щуп зовёт ``urllib.request.urlopen`` по месту, поэтому подменяем ровно его.
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    return asked


@pytest.mark.machine
def test_a_single_byte_of_the_stream_proves_the_swarm_is_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """У «Моаны 2» заголовок едет 17 с - это норма, и обрывать её нельзя."""
    _served(b"x" * 4096, monkeypatch)

    alive = swarm_pulse("http://torr/stream/hash-1/2", grace=0.0)
    for _ in range(200):  # нитка тянет байты в фоне
        if alive():
            break
        time.sleep(0.01)

    assert alive(), "байт пришёл - ждать ffprobe можно сколько угодно"


@pytest.mark.machine
def test_a_silent_swarm_stops_being_waited_for_after_the_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ни байта за отсрочку - пиров нет, и досиживать весь бюджет на таком релизе незачем."""
    _served(b"", monkeypatch)

    alive = swarm_pulse("http://torr/stream/hash-1/2", grace=0.05)

    assert alive(), "внутри отсрочки ждём"
    time.sleep(0.08)
    assert not alive(), "отсрочка вышла, а байтов нет"


@pytest.mark.machine
def test_only_the_head_of_the_file_is_pulled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подтвердить жизнь достаточно первым куском: сами байты тянут прогрев и показ."""
    asked = _served(b"x" * 4096, monkeypatch)

    alive = swarm_pulse("http://torr/stream/hash-1/2", grace=0.0)
    for _ in range(200):
        if alive():
            break
        time.sleep(0.01)

    assert asked, "запрос ушёл"
    assert asked[0].headers["Range"].startswith("bytes=0-"), "тянем голову, а не файл"


def test_the_wait_that_has_not_started_yet_is_not_counted_against_the_swarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отсрочку отсчитывают от того момента, когда ожидание метаданных и правда началось."""
    _served(b"", monkeypatch)

    class _Wait:
        activated_at = None

    alive = swarm_pulse("http://torr/stream/hash-1/2", grace=0.0, wait=_Wait())

    assert alive(), "ожидание ещё не начиналось - винить рой не в чем"
