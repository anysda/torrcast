"""Разбирает JSON-ответ агрегата ``/api/v1/search`` в строки сырой выдачи."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.collect_rows import collect_rows
from torrcast.adapters.prowlarr.torrent_links import LINKS
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.raw_result import RawResult
from torrcast.domain.twin_base import twin_base


def _tracker(name: Any) -> Any:
    """A twin's rows are its tracker's (:mod:`~torrcast.domain.twin_base`): one catalog."""
    return twin_base(name) if isinstance(name, str) else name


def from_json(payload: Any) -> list[RawResult]:
    """Разобрать ответ ``/api/v1/search``.

    Ответ агрегата - список строк; всё остальное значит, что мы разговариваем не с
    Prowlarr, и это отказ инфраструктуры, а не пустая полка каталога.
    """
    if not isinstance(payload, list):
        raise InfraError(phrase("prowlarr.unexpected_answer"))
    LINKS.remember(payload)
    return collect_rows(
        (
            i.get("title"),
            i.get("infoHash"),
            i.get("size"),
            i.get("seeders"),
            _tracker(i.get("indexer")),
        )
        for i in payload
        if isinstance(i, dict)
    )


__all__ = ["from_json"]
