"""Зеркало договора моста: коды ответа, которые читает интеграция Home Assistant."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from hass.refused_error import RefusedError
from hass.serve import serve


class _Bridge:
    """Мост из памяти: маршрут спрашивают у него, а он говорит, что его позвали."""

    def __init__(self) -> None:
        self.played: list[str] = []
        self.controlled: list[tuple[str, float]] = []
        self.nexted = 0
        self.refuse = ""

    def state(self) -> dict[str, Any]:
        return {"state": "idle", "title": None}

    def play(self, query: str) -> str:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.played.append(query)
        return "deadbeef"

    def control(self, command: str, arg: float) -> None:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.controlled.append((command, arg))

    def next(self) -> None:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.nexted += 1


@pytest.fixture
def bridge() -> _Bridge:
    return _Bridge()


@pytest.fixture
def address(bridge: _Bridge) -> Iterator[str]:
    """Настоящий сервер на свободном порту: договор меряется по проводу, а не по вызову."""
    server = serve(bridge, 0, "127.0.0.1")  # type: ignore[arg-type]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _call(url: str, method: str = "GET", body: bytes | None = None) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as answer:
            return int(answer.status), answer.read().decode("utf-8")
    except urllib.error.HTTPError as refusal:
        return int(refusal.code), refusal.read().decode("utf-8")


def test_the_snapshot_comes_back_as_json(address: str) -> None:
    code, body = _call(f"{address}/api/state")

    assert code == 200
    assert json.loads(body)["state"] == "idle"


def test_a_show_is_accepted_with_a_ticket(address: str, bridge: _Bridge) -> None:
    code, body = _call(f"{address}/api/play", "POST", json.dumps({"query": "муха"}).encode())

    assert code == 202
    assert json.loads(body)["key"]
    assert bridge.played == ["муха"]


def test_the_remote_and_the_next_episode_answer_without_a_body(
    address: str, bridge: _Bridge
) -> None:
    control = json.dumps({"cmd": "seekby", "arg": 90}).encode()

    assert _call(f"{address}/api/control", "POST", control) == (204, "")
    assert _call(f"{address}/api/next", "POST", b"") == (204, "")
    assert bridge.controlled == [("seekby", 90.0)]
    assert bridge.nexted == 1


def test_a_refusal_of_the_bridge_becomes_409_with_the_same_word(
    address: str, bridge: _Bridge
) -> None:
    bridge.refuse = "nothing_playing"
    control = json.dumps({"cmd": "toggle"}).encode()

    code, body = _call(f"{address}/api/control", "POST", control)

    assert code == 409
    assert json.loads(body) == {"error": "nothing_playing"}


def test_a_stranger_gets_404_405_and_400(address: str) -> None:
    assert _call(f"{address}/api/whatever")[0] == 404
    assert _call(f"{address}/api/state", "PUT", b"")[0] == 405
    assert _call(f"{address}/api/play", "POST", b"{ not json")[0] == 400
    # Слово пульта не из договора - тоже 400: молча взять «первое похожее» значило бы
    # нажать за зрителя чужую кнопку.
    assert _call(f"{address}/api/control", "POST", b'{"cmd": "explode"}')[0] == 400
    # Перемотка без числа - не перемотка на ноль.
    assert _call(f"{address}/api/control", "POST", b'{"cmd": "seekby"}')[0] == 400
