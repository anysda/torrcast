"""Дата первой публикации картины из Wikidata (P577); зовёт сценарий паспорта."""

from __future__ import annotations

from torrcast.adapters.wiki.endpoints import _SPARQL_HEAD, _WIKIDATA_HOST, _WIKIDATA_PATH
from torrcast.domain.facts.read_published import read_published
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.ports.json_client import JsonClient


class WikidataDates:
    """Тот же SPARQL и тот же клиент, что у хронометража справки."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def published(self, entity: str, timeout: float = HTTP_TIMEOUT) -> int | None:
        """Год первой публикации картины из Wikidata (P577); нет даты - ``None``.

        Дат у P577 бывает несколько (разные страны проката, издания) - берём самую раннюю:
        она и есть «первая публикация».
        """
        query = f"SELECT ?date WHERE {{ wd:{entity} wdt:P577 ?date }}"
        payload = self.client.get(
            _WIKIDATA_HOST, _WIKIDATA_PATH, {"query": query}, dict(_SPARQL_HEAD), timeout
        )
        return read_published(payload)
