"""Разбирает JSON-ответ агрегата ``/api/v1/search`` в строки сырой выдачи."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.domain.infra_error import InfraError


def from_json(payload: Any) -> list[RawResult]:
    """Разобрать ответ ``/api/v1/search``.

    Ответ агрегата - список строк; всё остальное значит, что мы разговариваем не с
    Prowlarr, и это отказ инфраструктуры, а не пустая полка каталога.
    """
    if not isinstance(payload, list):
        raise InfraError("Prowlarr вернул неожиданный ответ")
    return RawResult.collect(
        (i.get("title"), i.get("infoHash"), i.get("size"), i.get("seeders"), i.get("indexer"))
        for i in payload
        if isinstance(i, dict)
    )


__all__ = ["from_json"]
