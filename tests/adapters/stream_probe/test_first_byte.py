"""Первый байт записанного файла: пришёл, не пришёл за срок или службу спросить не удалось."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from typing import Any

import pytest

from torrcast.adapters.stream_probe.first_byte import first_byte


class _Answer:
    def __init__(self, payload: bytes, hold: threading.Event | None = None) -> None:
        self.payload = payload
        self.hold = hold

    def read(self, size: int) -> bytes:
        if self.hold is not None:
            self.hold.wait(5.0)
        return self.payload[:size]

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _served(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[Any]:
    asked: list[Any] = []

    def _open(request: Any, timeout: float = 0.0) -> _Answer:
        asked.append(request)
        if isinstance(answer, BaseException):
            raise answer
        return answer  # type: ignore[no-any-return]

    # Щуп зовёт ``urllib.request.urlopen`` по месту, поэтому подменяем ровно его.
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    return asked


@pytest.mark.machine
def test_a_byte_of_the_file_is_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Байт пришёл - раздача отдаёт; читается сам файл с нуля."""
    asked = _served(monkeypatch, _Answer(b"x" * 4096))

    assert first_byte("http://torr/stream/hash-1/2")(5.0) is True
    assert asked[0].full_url == "http://torr/stream/hash-1/2"
    assert asked[0].get_header("Range") == "bytes=0-"


@pytest.mark.machine
def test_no_byte_within_the_limit_is_a_no(monkeypatch: pytest.MonkeyPatch) -> None:
    """Служба держит соединение, а байта нет - за срок ответ «не пришёл»."""
    hold = threading.Event()
    _served(monkeypatch, _Answer(b"x", hold))
    arrived = first_byte("http://torr/stream/hash-1/2")

    assert arrived(0.05) is False
    hold.set()
    assert arrived(5.0) is True, "байт, пришедший позже, ждалка видит"


@pytest.mark.machine
@pytest.mark.parametrize(
    "answer",
    [_Answer(b""), urllib.error.URLError("connection refused"), TimeoutError("timed out")],
)
def test_a_refusing_service_gives_no_verdict(monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    """Пустой ответ, отказ или обрыв службы - «спросить не удалось», а не «мертво»."""
    _served(monkeypatch, answer)

    assert first_byte("http://torr/stream/hash-1/2")(5.0) is None
