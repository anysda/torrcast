"""Строки ленты и счёт индексеров, чьих строк в ней нет: опоздали или отказали.

Лента врозь (:func:`torrcast.adapters.prowlarr.feed_apart.feed_apart`) отдаёт то, что
успели принести за срок. Недосчитанный индексер - обещание: добор к сроку полки
(:mod:`web.feed_refill`) переспрашивает только его, и пока тот успевает, страница не
гасит счётчик.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from torrcast.domain.feed_row import FeedRow

#: Переспрос недосчитанных индексеров с ожиданием не дольше данных секунд.
Again = Callable[[float], "FeedRows"]


class FeedRows(list[FeedRow]):
    """Список строк ленты; ``missed`` - сколько индексеров недосчитано, ``again`` - их переспрос."""

    def __init__(
        self, rows: Iterable[FeedRow] = (), missed: int = 0, again: Again | None = None
    ) -> None:
        super().__init__(rows)
        self.missed = missed
        self.again = again


__all__ = ["Again", "FeedRows"]
