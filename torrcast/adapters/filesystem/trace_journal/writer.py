"""Фоновая запись ленты и единственный её экземпляр на процесс.

Кладут в него записи :func:`emit`, дожимает хвост :func:`shutdown`."""

from __future__ import annotations

import contextlib
import queue
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final

from torrcast.adapters.filesystem.trace_journal.flush import _flush
from torrcast.adapters.filesystem.trace_journal.log_path import log_path

if TYPE_CHECKING:
    from pathlib import Path

#: Очередь ограничена: если фоновый писатель отстаёт, запись роняется, но показ - никогда.
_QUEUE_MAX: Final = 4096
_BATCH: Final = 256
#: Чем поднимается фоновый поток. ``None`` в ответе значит «не поднялся»: следующая
#: запись попробует снова, а стенду так достаётся писатель без живого демона за спиной.
_Spawn = Callable[[Callable[[], None]], "threading.Thread | None"]
#: Куда кладётся запись ленты.
_Put = Callable[[dict[str, Any]], None]


def _daemon(run: Callable[[], None]) -> threading.Thread | None:
    """Боевой подъём фонового потока: демон, потому что хвост ленты показа не переживёт."""
    thread = threading.Thread(target=run, name="torrcast-trace", daemon=True)
    thread.start()
    return thread


class _Writer:
    """Фоновая запись ленты: :meth:`put` только кладёт в очередь, диск трогает :meth:`_run`.

    Разнесено намеренно - :meth:`put` зовут из горячего пути отдачи сегмента, и он обязан
    вернуться, не дожидаясь ни ``open``, ни ``flush``. Поток - демон: показ гасится, недопи-
    санный хвост ленты значения не имеет, а :func:`shutdown` при штатном выходе его дожимает.
    """

    def __init__(self, depth: int = _QUEUE_MAX, spawn: _Spawn = _daemon) -> None:
        #: В очереди лежит не запись, а ПАРА «файл ленты, запись»: см. :meth:`put`.
        self._q: queue.Queue[tuple[Path, dict[str, Any]] | None] = queue.Queue(maxsize=depth)
        self._spawn = spawn
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pruned = ""
        #: Сколько записей очередь не приняла. Счётчик без замка НАМЕРЕННО: он про уже
        #: сломавшийся случай, а цена в горячем пути обязана остаться нулевой - недосчёт
        #: на гонке дешевле замка в отдаче сегмента.
        self._lost = 0

    def put(self, record: dict[str, Any]) -> None:
        """ГОРЯЧИЙ ПУТЬ. Ровно одно: неблокирующая укладка в очередь. Ни байта на диск.

        🔴 СЛЕПАЯ ЗОНА. Очередь конечна (:data:`_QUEUE_MAX`), и переполнение роняет запись:
        показ важнее диагностики. Молча это больше не делается - потери считаются и уходят
        в ленту отдельной записью (``lost``), которую печатает и ``cast log``. Но и запись о
        потере не всесильна: сами потерянные события не восстановимы, и «в ленте нет строки»
        рядом с ``lost`` значит «строка могла быть съедена очередью», а не «события не было».

        Файл ленты выбирается ЗДЕСЬ и едет в очереди вместе с записью. Место записи - это
        свойство МОМЕНТА СОБЫТИЯ, а не момента, когда до диска дошли руки: писатель
        фоновый, между укладкой и записью проходит сколько угодно времени, и за это время
        каталог ленты (:data:`LOG_ENV`, файл состояния) может смениться, а сутки -
        перевалить за полночь. Выбирай файл писатель у себя, отставший хвост уезжал бы в
        чужую ленту. Диска это не касается: :func:`log_path` только считает путь.
        """
        if self._thread is None:
            self._start()
        try:
            self._q.put_nowait((log_path(), record))
        except queue.Full:
            self._lost += 1

    def _start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = self._spawn(self._run)

    def _run(self) -> None:
        while True:
            first = self._q.get()
            if first is None:
                return
            batch: list[tuple[Path, dict[str, Any]]] = [first]
            with contextlib.suppress(queue.Empty):
                while len(batch) < _BATCH:
                    nxt = self._q.get_nowait()
                    if nxt is None:
                        self._flush(batch)
                        return
                    batch.append(nxt)
            self._flush(batch)

    def drain(self) -> None:
        """Синхронно записать всё, что уже в очереди. Для :func:`shutdown` и тестов."""
        batch: list[tuple[Path, dict[str, Any]]] = []
        with contextlib.suppress(queue.Empty):
            while True:
                item = self._q.get_nowait()
                if item is not None:
                    batch.append(item)
        if batch or self._lost:  # признание в потерях дожимается даже с пустым хвостом
            self._flush(batch)

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            self.drain()
            return
        self._q.put(None)
        thread.join(timeout=2.0)
        self._thread = None

    def _flush(self, batch: list[tuple[Path, dict[str, Any]]]) -> None:
        """Пакет записей на диск и ротация каталогов (:func:`_flush`)."""
        lost, self._lost = self._lost, 0
        self._pruned = _flush(batch, lost, self._pruned)


_writer = _Writer()
#: Куда кладутся записи ленты в этом процессе. Пусто - значит в боевого писателя выше;
#: стенд ставит сюда подделку (``tests/fakes/composition.use_tape``). Схема события
#: ловится там, где запись уходит в очередь, а не на файле: файл пишет фоновый поток, и
#: его расписание к схеме отношения не имеет.
_tape: _Put | None = None


def _put(record: dict[str, Any]) -> None:
    """Положить запись туда, куда в этом процессе пишется лента."""
    (_writer.put if _tape is None else _tape)(record)
