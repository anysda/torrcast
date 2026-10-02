"""Дверь держателя записей к TorrServer: один вызов за раз и не во время подъёма показа.

🔴 TorrServer отвечает всем под одним замком: десять записей, продлевавшие аренду каждая
своим потоком (:mod:`web.record_hold`), клали в него пачку ``add`` с записью в базу, и клик
ждал её хвост. Замер на стенде: все 16 скоплений медленных вызовов (1-10 с) начинал
держатель, а показ «Рика» ждал свой ``add`` 10.3 с и сетку ещё 15.5 с - кадр через 33 с.
Поэтому вызовы держателя идут по одному, а пока показ поднимается
(:data:`~torrcast.usecases.start_progress.START`), новый не начинается вовсе: аренда живёт
:data:`web.record_hold.LEASE`, подъём её не съест. Ожидание ограничено :data:`YIELD`.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Final

from torrcast.usecases.start_progress import START

#: Дольше фоновый вызов подъём показа не ждёт: застрявший подъём не вправе снять аренды.
YIELD: Final = 60.0
#: Шаг, которым вызов за дверью спрашивает, поднялся ли показ.
STEP: Final = 0.5


def _starting() -> bool:
    return START.seen() is not None


@dataclass
class RecordDoor:
    """Очередь вызовов держателя к службе; подъём, часы и ожидание подставные ради тестов."""

    starting: Callable[[], bool] = _starting
    clock: Callable[[], float] = time.monotonic
    wait: Callable[[float], object] = time.sleep
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @contextlib.contextmanager
    def call(self) -> Iterator[None]:
        """Войти, когда подъёма нет (или он ждан :data:`YIELD`) и прошлый вызов вышел."""
        ends = self.clock() + YIELD
        while True:
            while self.starting() and self.clock() < ends:
                self.wait(STEP)
            self._lock.acquire()
            if not self.starting() or self.clock() >= ends:
                break
            self._lock.release()
        try:
            yield
        finally:
            self._lock.release()
