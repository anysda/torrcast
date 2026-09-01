"""Собирает адрес поискового запроса к Prowlarr: агрегат или один индексер."""

from __future__ import annotations

from typing import Final
from urllib.parse import quote

from torrcast.domain.wire_query import wire_query

#: Агрегат по всем индексерам. ⚠️ Выяснено на живом Prowlarr 2.5.2:
#: ``/api/v2.0/indexers/all/results`` - это Jackett, у Prowlarr на него 404.
SEARCH_PATH: Final = "/api/v1/search"
#: Кино, сериалы и «Other» - под последней RuTor отдаёт вообще всё (категорий у него нет).
#: Четвёртая добавлена ради источника, у которого вся выдача лежит под одной категорией:
#: без неё индексер отвечает, а раздачи не проходят фильтр вовсе.
CATEGORIES: Final = (2000, 5000, 6000, 8000)


def search_url(
    base_url: str, apikey: str, query: str, limit: int, indexer: int | None = None
) -> str:
    """Адрес поиска: без ``indexer`` - агрегат по всем, с ним - персональный запрос.

    Спрашиваем ровно то, что просили, но в форме, которую переживёт санитайзер Prowlarr
    (:func:`~torrcast.domain.wire_query.wire_query`, TC-129). Само название человеку не
    переписываем: в сообщениях и ключах состояния остаётся исходный запрос.
    """
    cats = "".join(f"&categories={c}" for c in CATEGORIES)
    one = f"&indexerIds={indexer}" if indexer is not None else ""
    return (
        f"{base_url}{SEARCH_PATH}?apikey={quote(apikey)}"
        f"&query={quote(wire_query(query))}&type=search&limit={limit}{cats}{one}"
    )


__all__ = ["CATEGORIES", "SEARCH_PATH", "search_url"]
