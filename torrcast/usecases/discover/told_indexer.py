"""Клиент индексеров, который помнит, что ему сказали: круг потом повторяется без сети.

Запись нужна дисковой памяти кругов (:mod:`web.circle_disk`): планы держат ручки живого
клиента, а строки каталога - простые данные, и тот же круг по ним собирается заново
(:class:`torrcast.usecases.discover.replay_indexer.ReplayIndexer`).
"""

from __future__ import annotations

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient

#: Один ответ клиента: что спросили (``search``/``late``/``spare``), строка запроса,
#: остаток цели, кого урезал потолок после этого захода и строки.
Told = tuple[str, str, float, tuple[str, ...], list[RawResult]]


class ToldIndexer:
    """Тот же клиент, но каждый его ответ ложится в :attr:`told` по порядку."""

    def __init__(self, inner: IndexerClient) -> None:
        self.inner = inner
        self.told: list[Told] = []

    @property
    def cap_floor(self) -> float:
        return self.inner.cap_floor

    @cap_floor.setter
    def cap_floor(self, value: float) -> None:
        self.inner.cap_floor = value

    @property
    def over_goal(self) -> bool:
        return self.inner.over_goal

    @over_goal.setter
    def over_goal(self, value: bool) -> None:
        self.inner.over_goal = value

    @property
    def capped(self) -> tuple[str, ...]:
        return tuple(getattr(self.inner, "capped", ()))

    def search(self, query: str) -> list[RawResult]:
        try:
            rows = self.inner.search(query)
        except NotFoundError:
            self.told.append(("search", query, 0.0, self.capped, []))
            raise
        self.told.append(("search", query, 0.0, self.capped, list(rows)))
        return rows

    def late(self) -> list[RawResult]:
        rows = self.inner.late()
        self.told.append(("late", "", 0.0, (), list(rows)))
        return rows

    def spare(self) -> float:
        spare = self.inner.spare()
        self.told.append(("spare", "", spare, (), []))
        return spare


__all__ = ["ToldIndexer"]
