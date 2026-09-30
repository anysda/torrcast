"""Лента по индексерам врозь и со сроком: залипший индексер не держит холодную полку.

Общий запрос Prowlarr отвечает, только когда опрошены ВСЕ индексеры (цену этого разбирает
:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`). Замер на стенде 30-09-2026:
Nyaa.si отвечал 502, Prowlarr повторял его до отказа, и лента холодной полки пришла через
43 с вместо обычных двух-трёх. Врозь молчун стоит только срока, а его строки подберёт
следующий заход добора ленты (:meth:`web.shelves_cache.ShelvesCache._rebuild`).

Срок не делает ленту пустой: не ответил за него никто - ждём первого ответившего.
Отказали все - это отказ каталога, и наверх уходит первый из отказов, как у общего запроса.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from torrcast.adapters.prowlarr.from_feed_json import from_feed_json
from torrcast.domain.feed_row import FeedRow


def _answered(ask: Future[Any]) -> bool:
    return ask.done() and ask.exception() is None


def feed_apart(get: Callable[[str], Any], urls: Sequence[str], within: float) -> list[FeedRow]:
    """Строки ленты от индексеров, ответивших за ``within`` секунд; раздача по хэшу одна.

    ``urls`` - адреса ленты, по одному на индексер; ``get`` - ответ по адресу. Опоздавшие
    дорабатывают в своих потоках и выбрасываются: ждать их - вернуть цену общего запроса.
    """
    pool = ThreadPoolExecutor(max(len(urls), 1), thread_name_prefix="feed-apart")
    asks = [pool.submit(get, url) for url in urls]
    pool.shutdown(wait=False)
    done, left = wait(asks, timeout=within)
    while left and not any(_answered(ask) for ask in done):
        more, left = wait(left, return_when=FIRST_COMPLETED)
        done |= more
    heard = [ask for ask in asks if ask in done and _answered(ask)]
    if not heard:
        failed = next((ask for ask in asks if ask in done and ask.exception() is not None), None)
        if failed is not None:
            raise failed.exception()  # type: ignore[misc]
        return []
    rows: dict[str, FeedRow] = {}
    for ask in heard:
        for row in from_feed_json(ask.result()):
            rows.setdefault(row.raw.info_hash.lower(), row)
    return list(rows.values())


__all__ = ["feed_apart"]
