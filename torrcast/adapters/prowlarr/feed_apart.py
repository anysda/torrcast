"""Лента по индексерам врозь и со сроком: залипший индексер не держит холодную полку.

Общий запрос Prowlarr отвечает, только когда опрошены ВСЕ индексеры (цену этого разбирает
:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`). Замер на стенде 30-09-2026:
Nyaa.si отвечал 502, Prowlarr повторял его до отказа, и лента холодной полки пришла через
43 с вместо обычных двух-трёх. Врозь молчун стоит только срока, а его строки подберёт
добор ленты к сроку полки (:mod:`web.feed_refill`): ``again`` спрашивает только недосчитанных.

Срок не делает ленту пустой: не ответил за него никто - ждём первого ответившего.
Отказали все - это отказ каталога, и наверх уходит первый из отказов, как у общего запроса.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from torrcast.adapters.prowlarr.from_feed_json import from_feed_json
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.feed_rows import Again, FeedRows


def _answered(ask: Future[Any]) -> bool:
    return ask.done() and ask.exception() is None


def _alive(ask: Future[Any]) -> bool:
    return not ask.done() or _answered(ask)  # still running, or late with its answer


def feed_apart(get: Callable[[str], Any], urls: Sequence[str], within: float) -> FeedRows:
    """Строки ленты от индексеров, ответивших за ``within`` секунд; раздача по хэшу одна.

    ``urls`` - адреса ленты, по одному на индексер; ``get`` - ответ по адресу. Опоздавшие
    дорабатывают в своих потоках и выбрасываются: ждать их - вернуть цену общего запроса.
    Их и отказавших ответ считает в ``missed``, а ``again`` переспрашивает только их.
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
        return FeedRows()
    rows: dict[str, FeedRow] = {}
    for ask in heard:
        for row in from_feed_json(ask.result()):
            rows.setdefault(row.raw.info_hash.lower(), row)
    missing = [(url, ask) for url, ask in zip(urls, asks, strict=True) if ask not in heard]
    return FeedRows(rows.values(), missed=len(missing), again=_again(get, missing))


def _again(get: Callable[[str], Any], left: list[tuple[str, Future[Any]]]) -> Again | None:
    """Переспрос только недосчитанных: опоздавшего ждём дальше, отказавшего спрашиваем снова."""
    if not left:
        return None

    def again(within: float) -> FeedRows:
        pool = ThreadPoolExecutor(len(left), thread_name_prefix="feed-again")
        asks = [ask if _alive(ask) else pool.submit(get, url) for url, ask in left]
        pool.shutdown(wait=False)
        done, _late = wait(asks, timeout=max(within, 0.0))
        rows: dict[str, FeedRow] = {}
        for ask in (ask for ask in asks if ask in done and _answered(ask)):
            for row in from_feed_json(ask.result()):
                rows.setdefault(row.raw.info_hash.lower(), row)
        still = [
            (url, ask)
            for (url, _was), ask in zip(left, asks, strict=True)
            if not (ask in done and _answered(ask))
        ]
        return FeedRows(rows.values(), missed=len(still), again=_again(get, still))

    return again


__all__ = ["feed_apart"]
