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

        🔴 Отказ сети поднимается наверх ИСКЛЮЧЕНИЕМ, а не пустым списком. Пустой список
        отсюда значит одно: Wikidata ответила, и родни у картины нет, - а такой ответ
        кладётся в кэш навсегда (:meth:`torrcast.usecases.franchise_kin.FranchiseKin.of`).
        Пока молчание сети приезжало сюда тем же пустым списком, одна оборванная связь
        гасила полку франшизы на всю жизнь установки: замер 07-09-2026 на стенде `.104` -
        «Форсаж» лёг в `facts.json` пустым рядом и отвечал пусто за 0,0 с, при том что
        живой запрос в ту же минуту давал десять картин.

        Чужой идентификатор до сети не доезжает вовсе - строка, не прошедшая
        :data:`_ENTITY_RE`, отвечает пустым списком на месте: это ответ, а не молчание.
        """
        if not _ENTITY_RE.match(entity):
            return []
        payload = self.client.get(
            WIKIDATA_HOST,
            WIKIDATA_PATH,
            {"query": kin_query(entity)},
            dict(SPARQL_HEAD),
            timeout,
        )
        return read_kin(payload)
