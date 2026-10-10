"""Спрос на раздачу: чтение с места, которого нет в кэше, и без падения на молчании."""

from __future__ import annotations

import urllib.request
from typing import Any

import pytest

import torrcast.adapters.stream_probe.swarm_demand as swarm_demand_module
from torrcast.adapters.stream_probe.swarm_demand import swarm_demand
from torrcast.adapters.torrserver.stream_reads import StreamReads


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
def test_the_demand_reads_from_the_asked_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[Any] = []
    answer = _Answer([b"x" * 1000, b"x" * 1000])

    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        asked.append(request)
        return answer

    monkeypatch.setattr(urllib.request, "urlopen", _open)

    swarm_demand("http://torr/stream/hash-1/2", offset=4096, seconds=0.5)

    assert asked[0].get_header("Range") == "bytes=4096-"
    assert not answer.chunks, "спрос читает, пока рой везёт"


@pytest.mark.machine
def test_a_silent_swarm_does_not_break_the_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        raise TimeoutError("рой молчит")

    monkeypatch.setattr(urllib.request, "urlopen", _open)

    swarm_demand("http://torr/stream/hash-1/2", offset=0, seconds=0.1)


#: Адрес ровно в том виде, в каком его строит ``TorrServer.stream_url``.
STREAM = "http://torr/stream?link=ABC123&index=2&play"


@pytest.mark.machine
def test_the_demand_reader_is_on_the_books_of_its_release(monkeypatch: pytest.MonkeyPatch) -> None:
    """Снятие раздачи (TC-1407) должно оборвать и спрос, иначе служба виснет на ``rem``."""
    reads = StreamReads()
    monkeypatch.setattr(swarm_demand_module, "READS", reads)
    seen: list[bool] = []

    class _Watched(_Answer):
        def read1(self, size: int) -> bytes:
            seen.append(reads.busy("abc123"))  # на учёте - снятие его дождётся
            return super().read1(size)

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=0.0: _Watched([b"x"]))

    swarm_demand(STREAM, offset=0, seconds=0.5)

    assert seen and all(seen)
    assert not reads.busy("abc123"), "кончив читать, спрос с учёта сходит"


@pytest.mark.machine
def test_a_cut_release_is_not_demanded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Снятую раздачу спрос не будит: запроса к службе нет вовсе."""
    reads = StreamReads()
    reads.close("abc123")
    monkeypatch.setattr(swarm_demand_module, "READS", reads)

    asked: list[Any] = []

    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        asked.append(request)
        return _Answer([b"x"])

    monkeypatch.setattr(urllib.request, "urlopen", _open)

    swarm_demand(STREAM, offset=0, seconds=0.1)

    assert not asked, "снятую раздачу не просят"
