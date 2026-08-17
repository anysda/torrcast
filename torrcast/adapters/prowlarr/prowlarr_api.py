"""Соединение с Prowlarr: адрес, ключ и одна сессия на весь поиск."""

from __future__ import annotations

from typing import Any, Final
from urllib.parse import quote

from torrcast.adapters.prowlarr.prowlarr_http_client import ProwlarrHttpClient
from torrcast.ports.torrent_index import IndexerHttpClient

#: Потолок общего запроса - того, которым спрашиваем, когда список индексеров недоступен.
#: Такой запрос отдаётся, только когда опрошены ВСЕ индексеры, поэтому потолок здесь - это
#: не «сколько ждём обычно» (обычно 1-3 с), а «сколько терпим одного залипшего». Прежние
#: 60 с рубили такой поиск начисто - вместе с находками остальных индексеров, то есть
#: ровно там, где ответ уже был.
TIMEOUT: Final = 150.0


class ProwlarrApi:
    """Куда и чем стучимся: одна сессия переживает все круги одного поиска."""

    def __init__(
        self,
        base_url: str,
        apikey: str,
        timeout: float = TIMEOUT,
        http: IndexerHttpClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.apikey = apikey
        self.timeout = timeout
        self.http: IndexerHttpClient = http or ProwlarrHttpClient()
        self.session: Any | None = None

    def open(self) -> Any:
        """Сессия, поднятая ДО потоков: ленивая её сборка внутри них - гонка."""
        if self.session is None:
            self.session = self.http.new_session()
        return self.session

    def url(self, path: str) -> str:
        """Адрес ручки Prowlarr вместе с ключом; ключ локальный, его заводит ``install.sh``."""
        return f"{self.base_url}{path}?apikey={quote(self.apikey)}"

    def get_json(self, url: str, timeout: float | None = None) -> Any:
        """Ответ ручки разобранным JSON; отказ приходит :class:`InfraError`."""
        return self.http.get_json(self.open(), url, timeout or self.timeout, self.base_url)

    def probe(
        self, indexer_url: str, test_url: str, list_timeout: float, test_timeout: float
    ) -> None:
        """Проверка индексера: ходит в источник по-настоящему и гасит истёкшую отсрочку."""
        self.http.probe(
            self.open(), indexer_url, test_url, list_timeout, test_timeout, self.base_url
        )


__all__ = ["TIMEOUT", "ProwlarrApi"]
