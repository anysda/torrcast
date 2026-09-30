"""Первые записи «Продолжить» греются до клика: карта, голова, начало ленты, кусок закладки.

Держатель (:mod:`web.record_hold`) поднимает раздачи записей ради метаданных, но байтов
не читает, и «Продолжить» платил с клика за первые куски роя: карту опорных кадров,
голову файла и кусок у закладки, до 36 с на стенде. Та же цепочка до клика
(:func:`torrcast.adapters.stream_pack.warm_file.warm_file`) даёт кадр за 2-3.5 с.

Греются первые :data:`~torrcast.domain.continue_row.WARM_ROW` записей ряда «Продолжить»,
каждая своей рукой. По одной они шли 10-28 с каждая, и третья не успевала к
клику за минуту: упор в задержку кусков роя, а не в полосу (4 МБ/с на три раздачи).
Прогрев уступает живому показу: пока юнит показа жив, новый не начинается, начатый
бросается на следующем мегабайте. Прогретая запись второй раз не греется, пока не
сдвинулась закладка.
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
    _busy: set[str] = field(default_factory=set, repr=False)
    _seen: tuple[float, bool] = field(default=(-STEP, False), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def name(self, magnets: list[str]) -> None:
        """Первые записи ряда; та же тройка ничего не обрывает, выпавшая бросается."""
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
            idle = [m for m in self._order if m in self._ready and m not in self._busy]
            self._busy.update(idle)
        for magnet in idle:
            self.spawn(partial(self._run, magnet))

    def _pick(self, magnet: str) -> WarmJob | None:
        return self._ready.get(magnet) if magnet in self._order else None

    def _still(self, job: WarmJob) -> bool:
        """Греть ли дальше: запись всё ещё ждёт этого прогрева и показа нет."""
        with self._lock:
            wanted = self._pick(job.magnet) == job
        return wanted and not self._show()

    def _show(self) -> bool:
        """Идёт ли показ; юнит спрашивается не чаще :data:`STEP` - прогрев зовёт на мегабайт."""
        with self._lock:
            at, live = self._seen
        now = self.clock()
        if now - at >= STEP:
            live = self.showing()
            with self._lock:
                self._seen = (now, live)
        return live

    def _run(self, magnet: str) -> None:
        while True:
            with self._lock:
                job = self._pick(magnet)
                if job is None:
                    self._busy.discard(magnet)
                    return
            if self._show():
                self.wait(STEP)
                continue
            began = self.clock()
            finished = threading.Event()
            alive = partial(self._still, job)
            self.warm(job.source, at=job.at, alive=alive, name=job.name, done=finished)
            finished.wait()
            whole = self._still(job)
            spent = round(self.clock() - began, 2)
            place = round(job.at)
            journal().mark("прогрев записи", файл=job.name, место=place, целиком=whole, за=spent)
            with self._lock:
                if whole:
                    self._done.add(job.mark)
                    if self._ready.get(job.magnet) == job:
                        del self._ready[job.magnet]
