"""Родня плиток опубликованной полки заранее: их Q-коды приехали вместе с полкой.

Плитка полки родни - картина, которую Wikidata уже назвала своим Q-кодом. Клик по ней
шёл прежним путём «имя → статья → Q-код → SPARQL», и родня стоила 1-3 с уже после
клика (замер CT501 14-09-2026). Здесь Q-код запоминается при публикации полки, а родня
её плиток снимается пачками в фоне, пока человек ещё выбирает.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from torrcast.domain.facts.kin import Kin

#: Картин в одном SPARQL: пачка из 25 отвечала за 2.6-8.6 с, одиночный запрос - 1-2 с.
BATCH: Final = 25
#: Полос Wikimedia под заранее снимаемую родню; остальные три остаются карточке.
LANES: Final = 2
#: Сколько картин ждёт в очереди: свежая полка встаёт первой, старый хвост отпадает.
QUEUE: Final = 200
#: Срок одной пачки: тяжёлая пачка идёт секунды, а ждёт её только фон.
TIMEOUT: Final = 30.0
Fetch = Callable[[list[str], float], object]
Spawn = Callable[[Callable[[], None]], None]


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="kin-ahead").start()


@dataclass
class KinAhead:
    """Q-коды плиток родни и фоновая очередь их полок; без ``fetch`` только помнит."""

    fetch: Fetch | None = None
    spawn: Spawn = _daemon
    _known: dict[tuple[str, int | None], str] = field(default_factory=dict, repr=False)
    _queue: list[str] = field(default_factory=list, repr=False)
    _seen: set[str] = field(default_factory=set, repr=False)
    _running: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def offer(self, found: Sequence[Kin]) -> None:
        """Запомнить Q-коды полки и поставить родню её плиток в очередь первой."""
        with self._lock:
            for kin in found:
                key = kin.name, kin.year
                # Два разных Q-кода под одним именем и годом - не тождество, а тёзки.
                known = self._known.get(key)
                self._known[key] = kin.entity if known in (None, kin.entity) else ""
            fresh = list(dict.fromkeys(k.entity for k in found if k.entity not in self._seen))
            self._seen.update(fresh)
            self._queue[:0] = fresh
            self._seen.difference_update(self._queue[QUEUE:])
            del self._queue[QUEUE:]
            workers = 0 if self.fetch is None else min(LANES - self._running, len(self._queue))
            self._running += max(workers, 0)
        for _ in range(workers):
            self.spawn(self._pump)

    def entity(self, title: str, year: int | None) -> str:
        """Q-код плитки родни с этим именем и годом; не встречалась или тёзки - пусто."""
        with self._lock:
            return self._known.get((title, year), "")

    def _pump(self) -> None:
        """Снимать пачки, пока очередь не опустеет; отказ вернёт их следующей полке."""
        while True:
            with self._lock:
                chunk = self._queue[:BATCH]
                del self._queue[:BATCH]
                if not chunk or self.fetch is None:
                    self._running -= 1
                    return
            try:
                self.fetch(chunk, TIMEOUT)
            except Exception:
                with self._lock:
                    self._seen.difference_update(chunk)


#: Одна память Q-кодов на процесс: её пишет полка родни, читают карточка и наведение.
KIN_AHEAD: Final = KinAhead()

__all__ = ["KIN_AHEAD", "KinAhead"]
