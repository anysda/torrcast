"""Сколько запросов клиент держит к одному хосту Wikimedia разом."""

from __future__ import annotations

import threading
import time

import pytest

from torrcast.adapters.wiki import http_json_client
from torrcast.adapters.wiki.http_json_client import HttpJsonClient


def _peak(monkeypatch: pytest.MonkeyPatch, host: str, callers: int = 8) -> int:
    lock = threading.Lock()
    now = [0]
    peak = [0]

    class _Reply:
        status = 200

        def getheader(self, _name: str) -> None:
            return None

        def read(self) -> bytes:
            return b"{}"

    class _Connection:
        def __init__(self, _host: str, **_kwargs: object) -> None:
            return None

        def request(self, *_args: object, **_kwargs: object) -> None:
            return None

        def getresponse(self) -> _Reply:
            with lock:
                now[0] += 1
                peak[0] = max(peak[0], now[0])
            time.sleep(0.05)
            with lock:
                now[0] -= 1
            return _Reply()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http_json_client, "_IPv4Connection", _Connection)
    client = HttpJsonClient("torrcast/test")
    asks = [
        threading.Thread(target=client.get, args=(host, "/w/api.php", {}, {}, 5.0, True))
        for _ in range(callers)
    ]
    for ask in asks:
        ask.start()
    for ask in asks:
        ask.join()
    return peak[0]


def test_wikipedia_gets_three_requests_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Живые соединения вдвое быстрее: пять полос слали 17-21 запрос в секунду и ловили 429."""
    assert _peak(monkeypatch, "ru.wikipedia.org") == 3


def test_wikidata_keeps_its_five(monkeypatch: pytest.MonkeyPatch) -> None:
    """Долгий SPARQL Wikidata не сужается заодно с Википедией."""
    assert _peak(monkeypatch, "query.wikidata.org") == 5
