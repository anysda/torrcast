"""Разбирает Torznab-RSS одного индексера в строки сырой выдачи."""

from __future__ import annotations

from typing import Final
from xml.etree import ElementTree

from torrcast.adapters.prowlarr.raw_result import RawResult, Row
from torrcast.domain.infra_error import InfraError

TORZNAB_NS: Final = "{http://torznab.com/schemas/2015/feed}"


def from_torznab(xml: str) -> list[RawResult]:
    """Разобрать Torznab-RSS: ``infohash`` и ``seeders`` лежат в ``torznab:attr``.

    Такую выдачу отдаёт запрос к одному индексеру (``/<id>/api``); он же путь
    совместимости с Jackett'ом - имя принёсшего лежит у них в разных тегах.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise InfraError(f"индексер вернул битый XML: {exc}") from exc
    rows: list[Row] = []
    for item in root.iter("item"):
        attrs = {a.get("name", ""): a.get("value", "") for a in item.iter(f"{TORZNAB_NS}attr")}
        indexer = item.findtext("prowlarrindexer") or item.findtext("jackettindexer") or ""
        title, size = item.findtext("title"), item.findtext("size")
        rows.append((title, attrs.get("infohash"), size, attrs.get("seeders"), indexer))
    return RawResult.collect(rows)


__all__ = ["TORZNAB_NS", "from_torznab"]
