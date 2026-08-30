"""Проверки двухходовой живой проверки Bot API."""

import signal

import requests
from pytest import MonkeyPatch

from tgbot.transport import transport


class _Response:
    def __init__(self, status: int, detail: str = "") -> None:
        self.status_code = status
        self.reason = detail
        self._detail = detail

    def json(self) -> dict[str, object]:
        return {"ok": self.status_code == 200, "description": self._detail}


def test_get_me_precedes_live_message(monkeypatch: MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def post(url: str, *, data: dict[str, str], **_rest: object) -> _Response:
        calls.append((url.rsplit("/", 1)[-1], data))
        return _Response(200)

    monkeypatch.setattr(requests, "post", post)
    result = transport("secret", "-100", "http://proxy:80", "hello")
    assert result.status == 200
    assert calls == [("getMe", {}), ("sendMessage", {"chat_id": "-100", "text": "hello"})]


def test_failed_get_me_never_sends(monkeypatch: MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> _Response:
        return _Response(401, "bad token")

    monkeypatch.setattr(requests, "post", post)
    assert transport("bad", "-100", "", "hello").status == 401


def test_total_deadline_interrupts_a_stuck_socket(monkeypatch: MonkeyPatch) -> None:
    handler: list[object] = []

    def arm(_kind: int, seconds: float) -> tuple[float, float]:
        if seconds:
            callback = handler[0]
            assert callable(callback)
            callback(signal.SIGALRM, None)
        return (0.0, 0.0)

    def install(_signal: int, callback: object) -> object:
        handler[:] = [callback]
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", install)
    monkeypatch.setattr(signal, "setitimer", arm)
    result = transport("token", "-100", "", "hello", timeout=0.01)
    assert (result.status, result.detail) == (0, "Timeout")
