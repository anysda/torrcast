"""Поручения моста: одно за раз, и исполняет их ГЛАВНЫЙ поток.

🔴 Команда показа идёт в ГЛАВНОМ потоке, как и у бота (:meth:`tgbot.bot.Bot.run_one`):
``cast`` ставит на время команды свой обработчик SIGTERM
(:func:`torrcast.cli.answered.answered`), а из чужого потока это не делается вовсе -
``signal only works in main thread``. Поэтому маршрут кладёт поручение сюда, а забирает
его точка входа моста (:func:`hass.main.main`) из главного потока.

Очереди у поручений нет: подъём показа идёт по одному, и второй заход - это отказ
(:meth:`Orders.take`). Исключение ровно одно, и оно названо своим именем:
:meth:`Orders.force` - остановка, отказать в которой нечем.

🔴 Остановка мимо очереди до идущего подъёма НЕ доходит: очередь дойдёт до неё только
когда подъём кончится, то есть через весь его бюджет старта. Поэтому отказ человека
живёт отдельным фактом (:meth:`Orders.abandon`), и спрашивает его сам подъём на своих
поворотах (:func:`torrcast.ports.abandon.slot.abandoned`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from queue import Queue

from tgbot.command_result import command_result
from torrcast.domain.why import why
from torrcast.usecases.start_progress import START

#: Команда продукта так, как её зовёт консоль: argv на входе, код возврата на выходе.
Command = Callable[[Sequence[str] | None], int]


class Orders:
    """Поручения моста по одному: очередь, защёлка подъёма и словесная причина отказа."""

    def __init__(self, command: Command) -> None:
        self._command = command
        self._lock = threading.Lock()
        self._queue: Queue[list[str] | None] = Queue()
        self._underway = False
        self._abandoned = False
        #: Отказ последнего поручения теми же словами, какими его сказала бы консоль.
        self.last_error = ""

    def underway(self) -> bool:
        """Идёт ли прямо сейчас подъём показа."""
        with self._lock:
            return self._underway

    def abandoned(self) -> bool:
        """Снят ли заказ на тот подъём, который идёт прямо сейчас.

        Спрашивает это сам подъём, из главного потока, пока он ещё идёт: очередь
        поручений до него в этот момент не дойдёт по устройству (см. модуль).
        """
        with self._lock:
            return self._abandoned

    def take(self, args: list[str]) -> bool:
        """Взять поручение в работу; занято подъёмом - ``False``, и это отказ моста."""
        with self._lock:
            if self._underway:
                return False
            self._underway = True
            # Отсюда же считает своё ожидание и страница: подъём взят в работу, и до
            # первого кадра идут те самые секунды, о которых она спрашивает
            # (:mod:`torrcast.usecases.start_progress`).
            START.began()
            self._abandoned = False  # отказ был от ПРОШЛОГО заказа, а не от этого
            self.last_error = ""  # прошлый отказ живёт до начала следующего показа
        self._queue.put(args)
        return True

    def abandon(self) -> bool:
        """Снять заказ на идущий подъём; отвечает, был ли он вообще.

        Ничего не ждёт и ничего не отменяет сама: кладёт факт, который подъём читает
        на ближайшем своём повороте. Подъёма нет - и снимать нечего.
        """
        with self._lock:
            if not self._underway:
                return False
            self._abandoned = True
            return True

    def settled(self, timeout: float) -> bool:
        """Дождаться, пока и подъём кончится, и очередь опустеет.

        Спрашивает это ровно один: показ, встающий поверх идущего
        (:func:`hass.starting.starting`), - и там же названо, почему ждать надо ДО
        :meth:`take`.
        """
        began = time.monotonic()
        while time.monotonic() - began < timeout:
            # `unfinished_tasks` - счётчик самой очереди, и спадает он в `task_done`, а
            # не когда поручение вынули. `empty()` тут соврал бы про идущую остановку:
            # она уже не в очереди, но ещё не сделана.
            if not self.underway() and self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return False

    def force(self, args: list[str]) -> None:
        """Положить поручение, не спрашивая занятости: остановке отказать нечем."""
        self._queue.put(args)

    def run(self) -> None:
        """Исполнять поручения, пока не попросят уйти. Зовётся из ГЛАВНОГО потока."""
        while self.run_one():
            pass

    def run_one(self) -> bool:
        """Исполнить одно поручение; ``False`` - в очередь положили просьбу уйти."""
        args = self._queue.get()
        try:
            if args is None:
                return False
            self._run(args)
            return True
        finally:
            self._queue.task_done()

    def leave(self) -> None:
        """Вывести цикл поручений из ожидания: мост уходит."""
        self._queue.put(None)

    def _run(self, args: list[str]) -> None:
        """Исполнить поручение и запомнить его отказ тем же словом, что и консоль.

        🔴 Снятый заказ отказом не считается. Человек сам попросил убрать этот подъём, и
        показывать ему за это отдельную жалобу не за что; а сказать её было бы нечем -
        отмена в консоль не пишет ни строки, и словом отказа стал бы голый код возврата.
        """
        try:
            result = command_result(self._command, args)
            if result.code and not self.abandoned():
                self.last_error = result.detail
        except Exception as error:
            self.last_error = why(error)
        finally:
            # Команда кончилась, а картинки на экране так и нет: отказ, отмена,
            # остановка. Ожидание больше ничьё, и держать его на экране страницы нечем.
            # Дошедший до экрана подъём сюда приходит уже замеренным - его считает не
            # конец команды, а первая живая секунда вкладки (:func:`web.position.position`).
            START.gone()
            with self._lock:
                self._underway = False
