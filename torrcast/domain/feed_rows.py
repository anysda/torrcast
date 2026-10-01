"""Строки ленты и счёт индексеров, чьих строк в ней нет: опоздали или отказали.

Лента врозь (:func:`torrcast.adapters.prowlarr.feed_apart.feed_apart`) отдаёт то, что
успели принести за срок. Недосчитанный индексер - обещание: следующий заход добора
(:meth:`web.shelves_cache.ShelvesCache._rebuild`) может собрать полку полнее, и страница
не вправе гасить счётчик раньше него.
"""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.feed_row import FeedRow


class FeedRows(list[FeedRow]):
    """Список строк ленты; ``missed`` - сколько индексеров в нём недосчитано."""

    def __init__(self, rows: Iterable[FeedRow] = (), missed: int = 0) -> None:
        super().__init__(rows)
        self.missed = missed


__all__ = ["FeedRows"]
