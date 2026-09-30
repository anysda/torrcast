"""Первые записи «Продолжить» греются до клика: карта, голова, начало ленты, кусок закладки.

Держатель (:mod:`web.record_hold`) поднимает раздачи записей ради метаданных, но байтов
не читает, и «Продолжить» платил с клика за первые куски роя: карту опорных кадров,
голову файла и кусок у закладки, до 36 с на стенде. Та же цепочка до клика
(:func:`torrcast.adapters.stream_pack.warm_file.warm_file`) даёт кадр за 2.5-4 с.

Греются первые :data:`~torrcast.domain.continue_row.WARM_ROW` записей, какие назвала
страница (карточка первой), и строго по одной: одна раздача получает всю полосу, а клик
достаётся одной плитке. Прогрев уступает живому показу: пока юнит показа жив, новый не
начинается, начатый бросается на следующем мегабайте. Прогретая запись второй раз не
греется, пока не сдвинулась закладка.
"""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Final

from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.domain.continue_row import WARM_ROW
from torrcast.ports.journal.slot import journal
from torrcast.ports.show_unit.slot import unit
from web.warm_job import WarmJob

#: Шаг, которым рука прогрева ждёт конца живого показа.
STEP: Final = 1.0


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="torrcast-record-warm", daemon=True).start()


def _showing() -> bool:
    with contextlib.suppress(Exception):  # не спросили - не показ: прогрев бросит сам рой
        return unit().active()
    return False


@dataclass
class RecordWarm:
    """Одна рука прогрева записей на процесс; прогрев, показ, часы и поток подставные."""

    warm: Callable[..., object] = warm_file
    showing: Callable[[], bool] = _showing
    clock: Callable[[], float] = time.monotonic
    wait: Callable[[float], object] = time.sleep
    spawn: Callable[[Callable[[], None]], None] = _thread
    _order: list[str] = field(default_factory=list, repr=False)
    _ready: dict[str, WarmJob] = field(default_factory=dict, repr=False)
    _done: set[tuple[str, str, int]] = field(default_factory=set, repr=False)
    _running: bool = field(default=False, repr=False)
    _seen: tuple[float, bool] = field(default=(-STEP, False), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def name(self, magnets: list[str]) -> None:
        """Записи, которые назвала страница, в её порядке; греются первые из них."""
        with self._lock:
            self._order = magnets[:WARM_ROW]
        self._start()

    def wants(self, magnet: str) -> bool:
        """Входит ли раздача в те, что греются."""
        with self._lock:
            return magnet in self._order

    def offer(self, job: WarmJob) -> None:
        """Раздача записи подключена и файл известен: можно греть."""
        with self._lock:
            if job.at <= 0 or job.mark in self._done or self._ready.get(job.magnet) == job:
                return
            self._ready[job.magnet] = job
        self._start()

    def forget(self, magnet: str) -> None:
        """Раздачу отпустили: греть её незачем, начатое бросается."""
        with self._lock:
            self._ready.pop(magnet, None)

    def _start(self) -> None:
        with self._lock:
            if self._running or self._pick() is None:
                return
            self._running = True
        self.spawn(self._run)

    def _pick(self) -> WarmJob | None:
        return next((self._ready[m] for m in self._order if m in self._ready), None)

    def _first(self, job: WarmJob) -> bool:
        """Греть ли дальше: запись всё ещё первая в очереди и показа нет."""
        with self._lock:
            ahead = self._pick() == job
        return ahead and not self._show()

    def _show(self) -> bool:
        """Идёт ли показ; юнит спрашивается не чаще :data:`STEP` - прогрев зовёт на мегабайт."""
        at, live = self._seen
        now = self.clock()
        if now - at >= STEP:
            live = self.showing()
            self._seen = (now, live)
        return live

    def _run(self) -> None:
        while True:
            with self._lock:
                job = self._pick()
                if job is None:
                    self._running = False
                    return
            if self._show():
                self.wait(STEP)
                continue
            began = self.clock()
            finished = threading.Event()
            alive = partial(self._first, job)
            self.warm(job.source, at=job.at, alive=alive, name=job.name, done=finished)
            finished.wait()
            whole = self._first(job)
            spent = round(self.clock() - began, 2)
            place = round(job.at)
            journal().mark("прогрев записи", файл=job.name, место=place, целиком=whole, за=spent)
            with self._lock:
                if whole:
                    self._done.add(job.mark)
                    if self._ready.get(job.magnet) == job:
                        del self._ready[job.magnet]
