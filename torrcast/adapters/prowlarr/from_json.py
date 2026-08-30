"""Разбирает JSON-ответ агрегата ``/api/v1/search`` в строки сырой выдачи."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.collect_rows import collect_rows
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.raw_result import RawResult


def from_json(payload: Any) -> list[RawResult]:
    """Разобрать ответ ``/api/v1/search``.

    Ответ агрегата - список строк; всё остальное значит, что мы разговариваем не с
    Prowlarr, и это отказ инфраструктуры, а не пустая полка каталога.
    """
    if not isinstance(payload, list):
        raise InfraError(phrase("prowlarr.unexpected_answer"))
    return collect_rows(
        (i.get("title"), i.get("infoHash"), i.get("size"), i.get("seeders"), i.get("indexer"))
        for i in payload
        if isinstance(i, dict)
    )


__all__ = ["from_json"]
