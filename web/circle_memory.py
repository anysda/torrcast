"""Память кругов раздач: найденное на срок, отказ «ничего не нашлось» на минуту, диск на сутки.

Пустой ответ помнится коротко, по образцу Torrentio (``addon/lib/cache.js``, Apache-2.0,
github.com/TheBeastLT/torrentio-scraper): без памяти отказа каждый переспрос карточки
картины без раздач заново гнал круг по индексерам, раз в секунду, пока открыта страница.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.told_circle import ToldCircle
from web.circle_disk import CircleDisk

if TYPE_CHECKING:
    from torrcast.usecases.discover.told_indexer import Told
    from torrcast.usecases.select.plan import Plan

#: Сколько помнится подтверждённое «ничего не нашлось».
EMPTY_TTL: Final = 60.0


@dataclass
class CircleMemory:
    """Согретые круги и свежие отказы; часы подставные ради тестов."""

    clock: Callable[[], float]
    ttl: float
    #: Диск кругов и сборка круга по записи; без них память живёт только в процессе.
    disk: CircleDisk | None = None
    replay: Callable[[str, list[Told]], list[Plan]] | None = None
    _found: dict[str, tuple[list[Plan], float]] = field(default_factory=dict, repr=False)
    _empty: dict[str, tuple[NotFoundError, float]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @staticmethod
    def key(query: str) -> str:
        """Один ключ круга на всех: поиск, прогрев, карточка и «похожие»."""
        return query.strip()

    def plans(self, query: str) -> list[Plan] | None:
        """Согретый круг, пустой список для свежего отказа, иначе ``None``."""
        key, now = self.key(query), self.clock()
        with self._lock:
            found = self._found.get(key)
            if found is not None and found[1] > now:
                return found[0]
            empty = self._empty.get(key)
            return [] if empty is not None and empty[1] > now else None

    def refusal(self, query: str) -> NotFoundError | None:
        """Свежий отказ этого запроса, если он есть."""
        with self._lock:
            empty = self._empty.get(self.key(query))
        return empty[0] if empty is not None and empty[1] > self.clock() else None

    def keep(self, query: str, plans: list[Plan]) -> None:
        """Запомнить непустую находку; пустая - не находка, урезанная - на минуту.

        Неполный круг (:meth:`poorer`) живой полный не вытесняет, а без него живёт минуту.
        """
        if not plans:
            return
        key, poorer = self.key(query), self.poorer(query, plans)
        with self._lock:
            live = self._found.get(key)
            if poorer and live is not None and live[1] > self.clock():
                return
            ttl = EMPTY_TTL if poorer or isinstance(plans, CutCircle) else self.ttl
            self._found[key] = (plans, self.clock() + ttl)
            self._empty.pop(key, None)

    def poorer(self, query: str, plans: list[Plan]) -> bool:
        """Промолчал ли в круге источник, чьи раздачи есть в записанном на диске.

        Метка урезанного (:class:`CutCircle`) ставится по отсечке переходника и пропускает
        ноль, пришедший раньше неё (JacRed: 0 за 3060 мс), а число строк честно гуляет.
        """
        told = plans.told if isinstance(plans, ToldCircle) else []
        kept = self.disk.told(self.key(query)) if self.disk is not None and told else None
        return bool(kept) and bool(_sources(kept or []) - _sources(told))

    def revive(self, query: str) -> list[Plan] | None:
        """Круг с диска, собранный заново без сети; ``None`` - записи нет или она стара."""
        if self.disk is None or self.replay is None:
            return None
        told = self.disk.told(self.key(query))
        try:
            plans = None if not told else self.replay(query, told)
        except TorrcastError:
            return None
        if not plans:
            return None
        plans = list(plans)  # a plain list: what came from disk is not written back
        with self._lock:
            self._found[self.key(query)] = (plans, self.clock() + self.ttl)
        return plans

    def store(self, query: str, plans: list[Plan]) -> None:
        """Записать полный круг на диск; урезанный, неполный и пустой туда не идут."""
        told = plans.told if isinstance(plans, ToldCircle) else []
        if self.disk is None or not plans or not told or isinstance(plans, CutCircle):
            return
        if not self.poorer(query, plans):
            self.disk.keep(self.key(query), told)

    def refuse(self, query: str, error: NotFoundError) -> None:
        """Запомнить «ничего не нашлось» на :data:`EMPTY_TTL`."""
        with self._lock:
            self._empty[self.key(query)] = (error, self.clock() + EMPTY_TTL)


def _sources(told: list[Told]) -> set[str]:
    return {
        name for said in told for row in said[4] for name in (*row.indexers, row.indexer) if name
    }


__all__ = ["EMPTY_TTL", "CircleMemory"]
