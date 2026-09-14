"""Память кругов раздач: найденное на срок, и отказ «ничего не нашлось» на минуту.

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

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan

#: Сколько помнится подтверждённое «ничего не нашлось».
EMPTY_TTL: Final = 60.0


@dataclass
class CircleMemory:
    """Согретые круги и свежие отказы; часы подставные ради тестов."""

    clock: Callable[[], float]
    ttl: float
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
        """Запомнить непустую находку; пустая - не находка."""
        if plans:
            with self._lock:
                self._found[self.key(query)] = (plans, self.clock() + self.ttl)
                self._empty.pop(self.key(query), None)

    def refuse(self, query: str, error: NotFoundError) -> None:
        """Запомнить «ничего не нашлось» на :data:`EMPTY_TTL`."""
        with self._lock:
            self._empty[self.key(query)] = (error, self.clock() + EMPTY_TTL)


__all__ = ["EMPTY_TTL", "CircleMemory"]
