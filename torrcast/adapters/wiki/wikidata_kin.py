"""Родня картины из Wikidata (P179, P155, P156); зовёт полку франшизы карточки."""

from __future__ import annotations

import re
from typing import Final

from torrcast.adapters.wiki.endpoints import SPARQL_HEAD, WIKIDATA_HOST, WIKIDATA_PATH
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.kin_query import kin_query
from torrcast.domain.facts.read_kin import read_kin
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.ports.json_client import JsonClient

#: Что вообще считается идентификатором Wikidata. Строка уезжает в ТЕЛО запроса SPARQL,
#: и чужой символ в ней - это чужой запрос, а не промах (та же мера, что у годов пачки).
_ENTITY_RE: Final = re.compile(r"^Q\d+$")


class WikidataKin:
    """Тот же SPARQL и тот же клиент, что у остальной справки Wikidata."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def kin(self, entity: str, timeout: float = HTTP_TIMEOUT) -> list[Kin]:
        """Другие части франшизы по Q-идентификатору картины; франшизы нет - пустой список.

        Отказ сети наверх не поднимается: несверенная родня означает «полка пуста», и это
        честнее, чем полка с обрывком ответа. Чужой идентификатор до сети не доезжает
        вовсе - строка, не прошедшая :data:`_ENTITY_RE`, отвечает пустым списком на месте.
        """
        if not _ENTITY_RE.match(entity):
            return []
        try:
            payload = self.client.get(
                WIKIDATA_HOST,
                WIKIDATA_PATH,
                {"query": kin_query(entity)},
                dict(SPARQL_HEAD),
                timeout,
            )
        except Exception:
            return []
        return read_kin(payload)
