"""Проверяет соединение с Prowlarr: одна сессия, ключ в адресе, свой таймаут."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.prowlarr_api import TIMEOUT, ProwlarrApi


class _Http:
    """Подставной HTTP-клиент: считает сессии и запоминает, о чём его просили."""

    def __init__(self) -> None:
        self.sessions = 0
        self.asked: list[tuple[Any, str, float, str]] = []
        self.probed: list[tuple[str, str, float, float]] = []

    def new_session(self) -> Any:
        self.sessions += 1
        return f"сессия {self.sessions}"

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        self.asked.append((session, url, timeout, base_url))
        return {"ok": True}

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        return None

    def probe(
        self,
        session: Any,
        indexer_url: str,
        test_url: str,
        list_timeout: float,
        test_timeout: float,
        base_url: str,
    ) -> None:
        self.probed.append((indexer_url, test_url, list_timeout, test_timeout))


def test_сессия_поднимается_один_раз_на_весь_поиск() -> None:
    """Ленивая сборка сессии внутри потоков круга - гонка, поэтому она общая."""
    http = _Http()
    api = ProwlarrApi("http://p/", "KEY", http=http)
    api.get_json("http://p/api/v1/search")
    api.get_json("http://p/api/v1/indexer")
    assert http.sessions == 1
    assert {session for session, *_rest in http.asked} == {"сессия 1"}


def test_адрес_ручки_несёт_ключ_и_обрезанный_корень() -> None:
    api = ProwlarrApi("http://p/", "KEY ключ", http=_Http())
    assert api.base_url == "http://p"
    assert (
        api.url("/api/v1/indexer")
        == "http://p/api/v1/indexer?apikey=KEY%20%D0%BA%D0%BB%D1%8E%D1%87"
    )


def test_свой_срок_запроса_сильнее_общего_потолка() -> None:
    """Личный бюджет индексера тем и работает, что заменяет общий потолок клиента."""
    http = _Http()
    api = ProwlarrApi("http://p", "KEY", http=http)
    api.get_json("http://p/one", 3.0)
    api.get_json("http://p/two")
    assert [timeout for _s, _u, timeout, _b in http.asked] == [3.0, TIMEOUT]


def test_проверка_индексера_идёт_той_же_сессией() -> None:
    http = _Http()
    api = ProwlarrApi("http://p", "KEY", http=http)
    api.probe("http://p/indexer/7", "http://p/indexer/test", 15.0, 10.0)
    assert http.probed == [("http://p/indexer/7", "http://p/indexer/test", 15.0, 10.0)]
    assert http.sessions == 1
