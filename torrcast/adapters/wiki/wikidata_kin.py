"""Родня картины из быстрого Wikidata API, без WDQS на пути карточки."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.adapters.wiki.endpoints import WIKIDATA_API_HOST, WIKIDATA_API_PATH
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue
from torrcast.ports.json_client import JsonClient

_ENTITY_RE: Final = re.compile(r"^Q\d+$")
_DATE_RE: Final = re.compile(r"([+-]?\d{4})-")
_GROUPS: Final = ("P179", "P8345")


class WikidataKin:
    """Серия: claims картины, обратный индекс и паспорта соседей пачками.

    ``P179`` сохраняет состав прежнего запроса для рядов фильмов. ``P8345`` нужен
    записям с прямой франшизой. ``P144`` и ``P1434`` не смешиваются с рядом: это
    общая основа и вселенная, которые расширяют полку несопоставимыми адаптациями.
    """

    def __init__(self, client: JsonClient) -> None:
        self.client = client

    def kin(self, entity: str, timeout: float = HTTP_TIMEOUT) -> list[Kin]:
        """Другие фильмы серии по QID; отказ сети остаётся исключением."""
        if not _ENTITY_RE.match(entity):
            return []
        source = self._entities([entity], "claims", timeout)
        record = json_map(json_map(json_map(source).get("entities")).get(entity))
        groups = [(prop, item) for prop in _GROUPS for item in _values(record.get("claims"), prop)]
        if not groups:
            return []
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            matches = list(pool.map(lambda pair: self._search(pair[0], pair[1], timeout), groups))
        ids = sorted({item for found in matches for item in found if item != entity})
        return self._kin(ids, timeout)

    def _search(self, prop: str, group: str, timeout: float) -> list[str]:
        """Элементы с тем же заявлением; проверенный QID не становится языком запроса."""
        payload = self._api(
            {
                "action": "query",
                "list": "search",
                "srnamespace": "0",
                "srlimit": "500",
                "srsearch": f"haswbstatement:{prop}={group}",
            },
            timeout,
        )
        rows = json_rows(json_map(json_map(payload).get("query")).get("search"))
        items = [str(json_map(row).get("title", "")) for row in rows]
        return [item for item in items if _ENTITY_RE.match(item)]

    def _kin(self, ids: list[str], timeout: float) -> list[Kin]:
        """Имена и годы приезжают ``wbgetentities``-пачками не более 50 QID."""
        found: list[Kin] = []
        for at in range(0, len(ids), 50):
            payload = self._entities(ids[at : at + 50], "labels|claims", timeout)
            records = json_map(json_map(payload).get("entities"))
            for item in ids[at : at + 50]:
                record = json_map(records.get(item))
                if name := _label(record):
                    found.append(Kin(item, name, _year(record)))
        return found

    def _entities(self, ids: list[str], props: str, timeout: float) -> JsonValue:
        return self._api({"action": "wbgetentities", "ids": "|".join(ids), "props": props}, timeout)

    def _api(self, params: dict[str, str], timeout: float) -> JsonValue:
        return self.client.get(
            WIKIDATA_API_HOST, WIKIDATA_API_PATH, {**params, "format": "json"}, {}, timeout
        )


def _values(claims: JsonValue, prop: str) -> list[str]:
    items = [_id(claim) for claim in json_rows(json_map(claims).get(prop))]
    return [item for item in items if _ENTITY_RE.match(item)]


def _id(claim: JsonValue) -> str:
    snak = json_map(json_map(claim).get("mainsnak"))
    value = json_map(json_map(snak.get("datavalue")).get("value"))
    return str(value.get("id", ""))


def _label(record: dict[str, JsonValue]) -> str:
    labels = json_map(record.get("labels"))
    russian = json_map(labels.get("ru")).get("value")
    english = json_map(labels.get("en")).get("value")
    return str(russian or english or "")


def _year(record: dict[str, JsonValue]) -> int | None:
    years = [
        int(match.group(1))
        for prop in ("P577", "P580")
        for claim in json_rows(json_map(record.get("claims")).get(prop))
        for match in [_date(claim)]
        if match
    ]
    return min(years) if years else None


def _date(claim: JsonValue) -> re.Match[str] | None:
    snak = json_map(json_map(claim).get("mainsnak"))
    data = json_map(snak.get("datavalue"))
    return _DATE_RE.match(str(data.get("value", "")))
