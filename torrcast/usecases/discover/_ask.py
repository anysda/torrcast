"""Один круг по индексерам."""

from __future__ import annotations

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient


def _ask(client: IndexerClient, query: str) -> list[RawResult]:
    """Один запрос к индексерам; пусто - это не ошибка, а повод переспросить иначе.

    Кто из индексеров молчит, у кого отказ и кто ещё в пути - человеку об этом не
    говорят: строки о составе каталога на экран не идут. Разбор от этого не страдает:
    круг целиком пишется в ленту (:mod:`torrcast.adapters.prowlarr.circle_trace`,
    поля ``got``, ``silent``, ``banned``, ``late``, ``ms``).
    """
    try:
        return client.search(query)
    except NotFoundError:
        return []
