"""Прогрев видимого: круг поиска и справка для плиток, которые человек уже видел.

Карточка спрашивает пул раздач тем же кругом, что и поиск (:mod:`web.card`): холодная полка
на стенде отвечала 2.3-12.1 с, и повтор стоил столько же. Здесь круг помнится, а тот, кто
дёргает его заранее по видимым плиткам (``POST /api/seen``), греет ЗАПРОС, а не плитку,
уступает живому (:meth:`WarmCache.take`), и новый экран заменяет очередь прошлого. Справка
греется по картинам согретого круга: карточка спрашивает её по имени картины, а не плитки.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from torrcast.domain.not_found_error import NotFoundError
from web.circle_disk import CircleDisk
from web.circle_memory import CircleMemory
from web.warm_live import _landed, _take_live
from web.warm_priority import _hint, _unasked, _warm_blurbs
from web.warm_pump import _pump

if TYPE_CHECKING:
    from torrcast.usecases.discover.told_indexer import Told
    from torrcast.usecases.facts import FactPicture
    from torrcast.usecases.select.plan import Plan

#: Сколько живёт согретый круг: экран греется за полминуты, и срок короче протухал бы
#: до клика, а час полки (:mod:`web.shelves_cache`) велик - по этим раздачам жмут «Играть».
TTL: Final = 300.0
#: Сколько кругов идёт фоном разом: пул индексеров у фона тот же, что у живого поиска, и
#: два фоновых круга растянули живой поиск на стенде с 8.3 с до 22.5 с, один - до 8.8 с.
WORKERS: Final = 1
#: Потолок экрана: сорока плиток человек за раз не видит.
LIMIT: Final = 40
#: Сколько фоновый рабочий ждёт живого, прежде чем оглядеться заново.
PATIENCE: Final = 5.0
#: Сколько живой запрос ждёт круг, который уже считает фон, прежде чем считать сам.
BUSY_WAIT: Final = 30.0


#: Кто считает круг, кто греет справку и кто уносит работу в фон (:mod:`web.warm_wiring`).
Circle = Callable[[str], "list[Plan]"]
Blurbs = Callable[["list[FactPicture]"], None]
Spawn = Callable[[Callable[[], None]], None]


@dataclass
class WarmCache:
    """Согретые круги и очередь на прогрев видимого; фон, часы и диск подставные в тестах."""

    circle: Circle
    blurbs: Blurbs
    spawn: Spawn
    clock: Callable[[], float] = time.monotonic
    ttl: float = TTL
    workers: int = WORKERS
    disk: CircleDisk | None = None
    replay: Callable[[str, list[Told]], list[Plan]] | None = None
    _memory: CircleMemory = field(init=False, repr=False)
    _queue: list[str] = field(default_factory=list, repr=False)
    _urgent: list[str] = field(default_factory=list, repr=False)
    _busy: set[str] = field(default_factory=set, repr=False)
    _stale: set[str] = field(default_factory=set, repr=False)
    _told: set[tuple[str, int | None]] = field(default_factory=set, repr=False)
    _running: int = field(default=0, repr=False)
    _live: int = field(default=0, repr=False)
    _cond: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def __post_init__(self) -> None:
        self._memory = CircleMemory(self.clock, self.ttl, self.disk, self.replay)

    def take(self, query: str, circle: Circle | None = None) -> list[Plan]:
        """Круг живому запросу: согретый - сразу, иначе считается тут же, вперёд фона.

        Один круг на запрос для поиска, прогрева, карточки и «похожих»: идущий дожидаются,
        второй веер делил бы пул с первым. ``circle`` - тот же круг с ходом внутрь (превью).
        """
        key = query.strip()
        with self._cond:
            # Only a running circle is waited for (a queued one is taken over), and a kept
            # circle being refreshed in the background is not waited for at all.
            self._cond.wait_for(
                lambda: key not in self._busy or self.ready(query) is not None, BUSY_WAIT
            )
            if (refused := self._memory.refusal(query)) is not None:
                raise refused
            ready = self.ready(query)
            if ready is not None and not self._memory.revived(query):
                return ready
            if ready is None:
                self._busy.add(key)
        if ready is not None:
            _hint(self, key, stale=True)  # shown from disk: the network refreshes it behind
            return ready
        with self._counting(query), self._hold():
            kept = self._memory.revive(query)
            plans = (circle or self.circle)(query) if kept is None else kept
        self._remember(query, plans, revived=kept is not None)
        if kept is not None:
            _hint(self, key, stale=True)  # served from disk at once, refreshed by the one hand
        return plans

    def take_live(self, query: str) -> list[Plan]:
        """Круг показу: только пришедший из сети (:func:`web.warm_live._take_live`)."""
        return _take_live(self, query, BUSY_WAIT)

    def landed(self, query: str) -> list[Plan] | None:
        """Живой круг или тот, что уже считается; ``None`` - считай свой (:mod:`web.warm_live`)."""
        return _landed(self, query, BUSY_WAIT)

    def ready(self, query: str) -> list[Plan] | None:
        """Согретый круг, ``[]`` при свежем «ничего не нашлось», иначе ``None``."""
        return self._memory.plans(query)

    def ask(self, screen: Sequence[str]) -> int:
        """Принять экран запросов: очередь становится ЭТИМ экраном, прошлая уступает.

        Возвращается число запросов в сеть: у выдачи поиска один на весь экран, у полки
        по одному на плитку, у согретого экрана - ноль.
        """
        queries: list[str] = []
        for row in screen[:LIMIT]:
            query = row.strip()
            if query and query not in queries and self.ready(query) is None:
                queries.append(query)
        with self._cond:
            self._queue = [
                query for query in queries if query not in self._busy and query not in self._urgent
            ]
            waiting = len(self._queue)
            hands = max(0, min(self.workers - self._running, waiting))
            self._running += hands
        for _ in range(hands):
            self.spawn(self._pump)
        return waiting

    def hint(self, query: str) -> int:
        return _hint(self, query)

    def _pump(self) -> None:
        _pump(self)

    def _quiet(self) -> None:
        """Дождаться, пока живой запрос отпустит сеть: фон второй в очереди, а не первый."""
        with self._cond:
            while self._live > 0:
                self._cond.wait(PATIENCE)

    @contextmanager
    def _counting(self, query: str) -> Iterator[None]:
        """Круг, который считает живой: «ничего» помнится минуту, ждущие будятся в конце."""
        try:
            yield
        except NotFoundError as nothing:
            self._memory.refuse(query, nothing)
            raise
        finally:
            with self._cond:
                self._busy.discard(query.strip())
                self._cond.notify_all()

    def _remember(self, query: str, plans: list[Plan], revived: bool = False) -> None:
        """Запомнить непустую находку и согреть справку её картин; пустая - не находка.

        Поднятое с диска уже лежит в памяти (:meth:`CircleMemory.revive`) и живым не зовётся.
        """
        if not plans:
            return
        if not revived:
            self._memory.keep(query, plans)
            self.spawn(lambda: self._memory.store(query, plans))
        wanted = _unasked(self, plans, LIMIT)
        if wanted:
            self.spawn(lambda: _warm_blurbs(self, wanted))

    @contextmanager
    def _hold(self) -> Iterator[None]:
        """Пока живёт этот кусок, фоновые рабочие не начинают нового круга."""
        with self._cond:
            self._live += 1
        try:
            yield
        finally:
            with self._cond:
                self._live -= 1
                self._cond.notify_all()


__all__ = ["LIMIT", "PATIENCE", "TTL", "WORKERS", "Blurbs", "Circle", "Spawn", "WarmCache"]
