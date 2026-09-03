"""Годы выхода пачки картин из Wikidata одним запросом; зовёт отбор постера.

Сосед (:class:`~torrcast.adapters.wiki.wikidata_dates.WikidataDates`) спрашивает про одну
картину и отдаёт самый ранний год - так его зовёт паспорт. Постеру нужно другое: он
сверяет год у ДЕСЯТКА находок сразу, и десяток запросов подряд превратил бы сверку из
дешёвой в дорогую. ``VALUES`` берёт всю пачку за один поход, а ответ приезжает
идентификатором и датой построчно.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from torrcast.adapters.wiki.endpoints import SPARQL_HEAD, WIKIDATA_HOST, WIKIDATA_PATH
from torrcast.domain.facts.in_budget import in_budget
from torrcast.domain.facts.read_years import read_years
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.ports.json_client import JsonClient

#: Что вообще считается идентификатором Wikidata. Проверка тут не педантизм: строка
#: уезжает в ТЕЛО запроса SPARQL, и чужой символ в ней - это чужой запрос, а не промах.
_ENTITY_RE: Final = re.compile(r"^Q\d+$")
#: Сколько картин влезает в один ``VALUES``. Десяток находок влезает целиком, а предел
#: стоит от длины адреса: запрос едет строкой параметра.
_BATCH: Final = 200
#: Сколько знаков идентификаторов везёт адрес запроса; та же мера, что и у Википедии.
_BUDGET: Final = 6000
#: Чем картина называет свой год. Дата публикации (``P577``) стоит у фильма, а у
#: СЕРИАЛА её не бывает вовсе: свой год он держит началом показа (``P580``). Пока
#: спрашивалась одна публикация, «Дюна» 2000 года отвечала пустотой, год оставался
#: несверенным - и мини-сериал терял постер при живой английской статье. Путь свойства
#: тут альтернатива, а не второй запрос: обе даты приезжают одним походом.
_WHEN: Final = "wdt:P577|wdt:P580"


class WikidataYears:
    """Тот же SPARQL и тот же клиент, что у хронометража справки, но пачкой."""

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def years(self, entities: Sequence[str], timeout: float = HTTP_TIMEOUT) -> dict[str, set[int]]:
        """Годы выхода по идентификатору картины; спрашивать не о чем - пустая карта.

        Отказ сети наверх не поднимается: несверенный год означает «постера нет», и
        это честнее, чем постер соседней картины. Различать 429 и картину без даты
        здесь нечем, а зовущему и не нужно - он ходит за той же картиной снова.
        """
        asked = [name for name in dict.fromkeys(entities) if _ENTITY_RE.match(name)]
        out: dict[str, set[int]] = {}
        for part in in_budget(asked, _BATCH, _BUDGET):
            values = " ".join(f"wd:{name}" for name in part)
            body = f"VALUES ?item {{ {values} }} ?item {_WHEN} ?date"
            query = f"SELECT ?item ?date WHERE {{ {body} }}"
            try:
                payload = self.client.get(
                    WIKIDATA_HOST, WIKIDATA_PATH, {"query": query}, dict(SPARQL_HEAD), timeout
                )
            except Exception:
                continue
            for entity, seen in read_years(payload).items():
                out.setdefault(entity, set()).update(seen)
        return out
