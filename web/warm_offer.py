"""Хвост очереди прогрева, который не меняет видимый экран."""

from __future__ import annotations

from collections.abc import Sequence

from web.warm_cache import LIMIT, WarmCache


def offer(cache: WarmCache, queries: Sequence[str]) -> int:
    """Добавить родню после видимых плиток, а не заменить их как новый экран.

    Следующий :meth:`WarmCache.ask` сотрёт и этот хвост: пришедшая прокрутка всегда
    важнее родни старой карточки. Отдельный модуль держит кэш коротким, а правило
    очереди - рядом с единственным нестандартным её заказчиком.
    """
    with cache._cond:
        added = [
            query.strip()
            for query in queries
            if query.strip()
            and query.strip() not in cache._queue
            and query.strip() not in cache._busy
            and cache.ready(query) is None
        ]
        room = max(0, LIMIT - len(cache._queue))
        cache._queue.extend(added[:room])
        waiting = len(added[:room])
        hands = max(0, min(cache.workers - cache._running, waiting))
        cache._running += hands
    for _ in range(hands):
        cache.spawn(cache._pump)
    return waiting


__all__ = ["offer"]
