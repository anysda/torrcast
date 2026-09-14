"""Клиент индексеров из записи: тот же круг второй раз, но без единого захода в сеть.

Запись делает :class:`torrcast.usecases.discover.told_indexer.ToldIndexer`. Ответ отдаётся
тому же вопросу и в том же порядке; вопроса, которого в записи не было, каталог «не знает».
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.told_indexer import Told


class ReplayIndexer:
    """Отвечает записанным; опоздавших у повтора нет, цель не тратится."""

    def __init__(self, told: Sequence[Told]) -> None:
        self._told = list(told)
        self.cap_floor = 0.0
        self.over_goal = False
        self.capped: tuple[str, ...] = ()

    def search(self, query: str) -> list[RawResult]:
        said = self._next("search", query)
        if said is None or not said[4]:
            raise NotFoundError(query)
        self.capped = said[3]
        return list(said[4])

    def late(self) -> list[RawResult]:
        said = self._next("late", "")
        return [] if said is None else list(said[4])

    def spare(self) -> float:
        said = self._next("spare", "")
        return 0.0 if said is None else said[2]

    def _next(self, kind: str, query: str) -> Told | None:
        for at, said in enumerate(self._told):
            if said[0] == kind and said[1] == query:
                return self._told.pop(at)
        return None


__all__ = ["ReplayIndexer"]
