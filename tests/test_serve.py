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
        self.picked: list[int | None] = []
        self.searched: list[str] = []
        self.results: list[dict[str, Any]] = []
        self.controlled: list[tuple[str, float]] = []
        self.nexted = 0
        self.resumed = 0
        self.refuse = ""
        self.pictures: dict[str, tuple[bytes, str]] = {}
        self.asked: list[str] = []

    def state(self) -> dict[str, Any]:
        return {"state": "idle", "title": None}

    def search(self, query: str) -> list[dict[str, Any]]:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.searched.append(query)
        return self.results

    def play(self, query: str, pick: int | None = None) -> str:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.played.append(query)
        self.picked.append(pick)
        return "deadbeef"

    def resume(self) -> str:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.resumed += 1
        return "cafebabe"

    def control(self, command: str, arg: float) -> None:
        if self.refuse:
            raise RefusedError(self.refuse)
        self.controlled.append((command, arg))

    def poster(self, name: str) -> tuple[bytes, str] | None:
        self.asked.append(name)
        return self.pictures.get(name)

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


def _bytes(url: str) -> tuple[int, bytes, str]:
    """Ответ маршрута картинки как есть: код, тело и объявленный тип.

    Отдельно от :func:`_call` намеренно: тот раскодирует тело как текст, а картинка
    текстом не является - декодирование её байтов упало бы раньше самой проверки.
    """
    try:
        with urllib.request.urlopen(url, timeout=5) as answer:
            return int(answer.status), answer.read(), answer.headers.get("Content-Type", "")
    except urllib.error.HTTPError as refusal:
        return int(refusal.code), refusal.read(), refusal.headers.get("Content-Type", "")


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


def test_a_search_lists_what_the_bridge_found(address: str, bridge: _Bridge) -> None:
    bridge.results = [
        {"pick": 1, "key": "movie:матрица:1999", "title": "Матрица", "year": 1999, "kind": "movie"}
    ]

    code, body = _call(f"{address}/api/search", "POST", json.dumps({"query": "матрица"}).encode())

    assert code == 200
    assert json.loads(body) == {"results": bridge.results}
    assert bridge.searched == ["матрица"]


def test_a_search_without_a_query_is_400(address: str) -> None:
    code, body = _call(f"{address}/api/search", "POST", b"{}")

    assert code == 400
    assert json.loads(body) == {"error": "no_query"}


def test_a_search_refusal_becomes_409_with_the_products_own_word(
    address: str, bridge: _Bridge
) -> None:
    bridge.refuse = "по запросу «матрица» ничего не нашлось"

    code, body = _call(f"{address}/api/search", "POST", json.dumps({"query": "матрица"}).encode())

    assert code == 409
    assert json.loads(body) == {"error": bridge.refuse}


def test_play_carries_the_pick_from_search_into_the_show(address: str, bridge: _Bridge) -> None:
    play = json.dumps({"query": "матрица", "pick": 2}).encode()

    code, body = _call(f"{address}/api/play", "POST", play)

    assert code == 202
    assert json.loads(body)["key"]
    assert bridge.played == ["матрица"]
    assert bridge.picked == [2]


def test_play_without_a_pick_still_auto_picks(address: str, bridge: _Bridge) -> None:
    _call(f"{address}/api/play", "POST", json.dumps({"query": "матрица"}).encode())

    assert bridge.picked == [None]


def test_carrying_on_needs_no_query_while_a_show_by_name_still_does(
    address: str, bridge: _Bridge
) -> None:
    """Продолжение едет своим маршрутом, а показ ПО ЗАПРОСУ пустого запроса не берёт."""
    code, body = _call(f"{address}/api/resume", "POST", b"")

    assert code == 202
    assert json.loads(body)["key"]
    assert bridge.resumed == 1
    empty, said = _call(f"{address}/api/play", "POST", json.dumps({"query": "  "}).encode())
    assert empty == 400
    assert json.loads(said) == {"error": "no_query"}
    assert bridge.played == []


def test_a_bad_pick_is_400_and_never_reaches_the_bridge(address: str, bridge: _Bridge) -> None:
    for bad in (0, -1, "2", 1.5, True):
        code, body = _call(
            f"{address}/api/play", "POST", json.dumps({"query": "матрица", "pick": bad}).encode()
        )
        assert code == 400, bad
        assert json.loads(body) == {"error": "bad_pick"}
    assert bridge.played == []


def test_the_picture_comes_back_as_bytes_with_its_own_type(address: str, bridge: _Bridge) -> None:
    """🔴 Картинку раздаёт САМ серв: наружу за ней Home Assistant не ходит.

    Тип объявляется тот, что прочитан у самих байтов: скажи «image/jpeg» на PNG - и
    карточка нарисует битую картинку, а серв будет считать, что всё отдал.
    """
    body = b"\x89PNG\r\n\x1a\n" + b"poster" * 10
    bridge.pictures["2f8c1d"] = (body, "image/png")

    code, got, kind = _bytes(f"{address}/api/poster/2f8c1d")

    assert (code, got, kind) == (200, body, "image/png")
    assert bridge.asked == ["2f8c1d"]


def test_a_picture_the_bridge_never_found_is_404(address: str, bridge: _Bridge) -> None:
    """🔴 Имя приезжает снаружи, и путём на диске оно не становится.

    Мост знает только те картинки, которые нашёл сам; всё остальное - чужое имя, и
    отвечает ему тот же 404, что и любому неизвестному маршруту.
    """
    assert _bytes(f"{address}/api/poster/2f8c1d")[0] == 404
    assert _bytes(f"{address}/api/poster/../../etc/passwd")[0] == 404
    assert _bytes(f"{address}/api/poster/")[0] == 404


def test_the_snapshot_route_is_not_confused_with_the_picture_route(
    address: str, bridge: _Bridge
) -> None:
    """Разбор идёт по началу пути, а снимок остаётся ровным адресом без хвоста."""
    assert _call(f"{address}/api/state")[0] == 200
    assert _call(f"{address}/api/state/2f8c1d")[0] == 404
    assert bridge.asked == []
