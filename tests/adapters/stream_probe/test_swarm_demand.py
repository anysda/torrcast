"""Скорость роя под спросом: меряется то, что пришло, с места, которого нет в кэше."""

from __future__ import annotations

import urllib.request
from typing import Any

import pytest

from torrcast.adapters.stream_probe.swarm_demand import swarm_demand


class _Answer:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def read1(self, size: int) -> bytes:
        return self.chunks.pop(0)[:size] if self.chunks else b""

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


@pytest.mark.machine
def test_the_bytes_that_came_are_counted_from_the_asked_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[Any] = []

    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        asked.append(request)
        return _Answer([b"x" * 1000, b"x" * 1000])

    monkeypatch.setattr(urllib.request, "urlopen", _open)

    speed = swarm_demand("http://torr/stream/hash-1/2", offset=4096, seconds=0.5)

    assert asked[0].get_header("Range") == "bytes=4096-"
    assert speed == pytest.approx(2000 / 0.5, rel=0.2)


@pytest.mark.machine
def test_a_silent_swarm_measures_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        raise TimeoutError("рой молчит")

    monkeypatch.setattr(urllib.request, "urlopen", _open)

    assert swarm_demand("http://torr/stream/hash-1/2", offset=0, seconds=0.1) == 0.0
