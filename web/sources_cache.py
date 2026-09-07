"""Серверный кэш числа включённых индексеров: строится фоном, отдаётся мгновенно.

``GET /api/web/sources`` не вправе ждать Prowlarr (TC-1110, тот же запрет, что и у
:mod:`web.shelves_cache`): строка «Ищем в N источниках…» стоит над результатами поиска
на каждом заходе, и поход в сеть на этом месте был бы ровно тем зависанием, от которого
уводит круг поиска врозь. Число до первой сборки честно равно нулю - фон ещё не успел
ни разу спросить список, а не подделка под живой счёт.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.torrcast_error import TorrcastError

#: Кто считает включённые индексеры; в бою - :func:`web.sources._count`.
Count = Callable[[], int]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="sources-cache").start()


@dataclass
class SourcesCache:
    """Число источников в памяти: обновляет его фон раз в час, читает - каждый запрос.

    Фон и сон - подставные ради тестов (:mod:`tests.thread_guard` роняет тест, следующий
    за тем, что оставил настоящий поток жить): подделка зовёт ``spawn`` и ``sleep``
    синхронно, ни разу не открывая настоящий сокет.
    """

    count: Count
    every: float = 3600.0
    spawn: Spawn = _daemon
    sleep: Callable[[float], None] = time.sleep
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _value: int = field(default=0, repr=False, compare=False)
    _started: bool = field(default=False, repr=False, compare=False)

    def get(self) -> int:
        """Число источников сразу из памяти; до первой сборки - честный ноль."""
        self._ensure_started()
        with self._lock:
            return self._value

    def _ensure_started(self) -> None:
        """Фон встаёт один раз, при первом же обращении - не при создании предмета."""
        with self._lock:
            if self._started:
                return
            self._started = True
        self.spawn(self._loop)

    def _loop(self) -> None:
        while True:
            self._rebuild()
            self.sleep(self.every)

    def _rebuild(self) -> None:
        """Пересчитать число источников; отказ Prowlarr не роняет цикл - следующий час свой."""
        try:
            value = self.count()
        except TorrcastError:
            return
        with self._lock:
            self._value = value


__all__ = ["Count", "SourcesCache", "Spawn"]
