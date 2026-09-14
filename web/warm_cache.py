"""Прогрев видимого: круг поиска и справка для плиток, которые человек уже видел.

Карточка спрашивает пул раздач заново тем же кругом, что и поиск (:mod:`web.card`), и
весь её ответ упирается в этот круг: холодная полка на стенде отвечала 2.3-12.1 с, а
повтор того же ключа стоил столько же - кэша у круга не было вовсе. Здесь он заводится,
и рядом с ним тот, кто дёргает круг ЗАРАНЕЕ, по плиткам, которые страница видит на
экране (``POST /api/seen``, :mod:`web.seen`). Правил три, и все про меру:
греется ЗАПРОС, а не плитка (у выдачи поиска он один на весь экран), живое идёт
вперёд очереди (:meth:`WarmCache.take`), а новый экран заменяет очередь прошлого.
Справка греется по картинам СОГРЕТОГО КРУГА, а не по надписи на плитке: карточка
спрашивает её по имени картины, а имя это у полки другое - на стенде плитка звалась
``The Shawshank Redemption``, а карточка искала ``Побег из Шоушенка``, и согретое по
плитке не доставалось никому. Пакетом же потому, что источник отвечает пакетом, и
двенадцать картин стоят там столько же, сколько одна (:class:`torrcast.usecases.facts.Facts`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.circle_memory import CircleMemory
from web.warm_priority import _hint, _unasked, _warm_blurbs

if TYPE_CHECKING:
    from torrcast.usecases.facts import FactPicture
    from torrcast.usecases.select.plan import Plan

#: Сколько живёт согретый круг: экран греется за полминуты, и срок короче протухал бы
#: до клика, а час полки (:mod:`web.shelves_cache`) велик - по этим раздачам жмут «Играть».
TTL: Final = 300.0
#: Сколько кругов идёт фоном разом. Круг - веер по всему пулу индексеров, и пул у фона
#: тот же, что у живого поиска: два фоновых круга растянули живой поиск на стенде с 8.3 с
#: до 22.5 с (медианы трёх пар, свежие запросы), один - с 8.0 с до 8.8 с. Экран из
#: шестнадцати плиток одна рука греет около полутора минут, и это дешевле, чем втрое
#: медленнее отвечающая строка поиска.
WORKERS: Final = 1
#: Потолок экрана: сорока плиток человек за раз не видит, а очередь длиннее грела бы то,
#: до чего он ещё не долистал.
LIMIT: Final = 40
#: Сколько фоновый рабочий ждёт живого, прежде чем оглядеться заново.
PATIENCE: Final = 5.0
#: Сколько живой запрос ждёт круг, который уже считает фон, прежде чем считать сам.
BUSY_WAIT: Final = 30.0


#: Кто считает круг, кто греет справку пакетом и кто уносит работу в фон; боевых
#: троих собирает :mod:`web.warm_wiring`.
Circle = Callable[[str], "list[Plan]"]
Blurbs = Callable[["list[FactPicture]"], None]
Spawn = Callable[[Callable[[], None]], None]


@dataclass
class WarmCache:
    """Согретые круги в памяти и очередь на прогрев видимого.

    Фон и часы - подставные ради тестов (:mod:`tests.thread_guard`): подделка зовёт
    ``spawn`` синхронно, ни разу не открывая настоящий сокет.
    """

    circle: Circle
    blurbs: Blurbs
    spawn: Spawn
    clock: Callable[[], float] = time.monotonic
    ttl: float = TTL
    workers: int = WORKERS
    _memory: CircleMemory = field(init=False, repr=False)
    _queue: list[str] = field(default_factory=list, repr=False)
    _urgent: list[str] = field(default_factory=list, repr=False)
    _busy: set[str] = field(default_factory=set, repr=False)
    _told: set[tuple[str, int | None]] = field(default_factory=set, repr=False)
    _running: int = field(default=0, repr=False)
    _live: int = field(default=0, repr=False)
    _cond: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def __post_init__(self) -> None:
        self._memory = CircleMemory(clock=self.clock, ttl=self.ttl)

    def take(self, query: str, circle: Circle | None = None) -> list[Plan]:
        """Круг живому запросу: согретый - сразу, иначе считается тут же, вперёд фона.

        Один круг на запрос для поиска, прогрева, карточки и «похожих»: идущий дожидаются,
        второй веер делил бы пул с первым. ``circle`` - тот же круг с ходом внутрь (превью).
        """
        key = query.strip()
        with self._cond:
            # Only a circle that is really running is waited for. A queued one is taken over:
            # it waited for the one hand to finish another tile's circle first.
            self._cond.wait_for(lambda: key not in self._busy, timeout=BUSY_WAIT)
            if (refused := self._memory.refusal(query)) is not None:
                raise refused
            if (ready := self.ready(query)) is not None:
                return ready
            self._busy.add(key)
        try:
            with self._hold():
                plans = (circle or self.circle)(query)
            self._remember(query, plans)
        except NotFoundError as nothing:
            self._memory.refuse(query, nothing)
            raise
        finally:
            with self._cond:
                self._busy.discard(key)
                self._cond.notify_all()
        return plans

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
        """Брать из очереди, пока она не кончится, уступая дорогу живому запросу."""
        try:
            while True:
                self._quiet()
                with self._cond:
                    if not self._urgent and not self._queue:
                        return
                    query = self._urgent.pop(0) if self._urgent else self._queue.pop(0)
                    if query in self._busy or self.ready(query) is not None:
                        continue  # a live caller already runs or landed this very circle
                    self._busy.add(query)
                try:
                    plans = self.circle(query)
                except NotFoundError as nothing:
                    self._memory.refuse(query, nothing)
                    plans = []
                except (TorrcastError, OSError):
                    plans = []
                self._remember(query, plans)
                with self._cond:
                    self._busy.discard(query)
                    self._cond.notify_all()
        finally:
            with self._cond:
                self._running -= 1

    def _quiet(self) -> None:
        """Дождаться, пока живой запрос отпустит сеть: фон второй в очереди, а не первый."""
        with self._cond:
            while self._live > 0:
                self._cond.wait(PATIENCE)

    def _remember(self, query: str, plans: list[Plan]) -> None:
        """Запомнить непустую находку и согреть справку её картин; пустая - не находка."""
        if not plans:
            return
        self._memory.keep(query, plans)
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
