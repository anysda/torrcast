"""Поручения моста: одно за раз, и исполняет их ГЛАВНЫЙ поток.

🔴 Команда показа идёт в ГЛАВНОМ потоке, как и у бота (:meth:`tgbot.bot.Bot.run_one`):
``cast`` ставит на время команды свой обработчик SIGTERM
(:func:`torrcast.cli.answered.answered`), а из чужого потока это не делается вовсе -
``signal only works in main thread``. Поэтому маршрут кладёт поручение сюда, а забирает
его точка входа моста (:func:`hass.main.main`) из главного потока.

Очереди у поручений нет: подъём показа идёт по одному, и второй заход - это отказ
(:meth:`Orders.take`). Исключение ровно одно, и оно названо своим именем:
:meth:`Orders.force` - остановка, отказать в которой нечем.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from queue import Queue

from tgbot.command_result import command_result
from torrcast.domain.why import why

#: Команда продукта так, как её зовёт консоль: argv на входе, код возврата на выходе.
Command = Callable[[Sequence[str] | None], int]


class Orders:
    """Поручения моста по одному: очередь, защёлка подъёма и словесная причина отказа."""

    def __init__(self, command: Command) -> None:
        self._command = command
        self._lock = threading.Lock()
        self._queue: Queue[list[str] | None] = Queue()
        self._underway = False
        #: Отказ последнего поручения теми же словами, какими его сказала бы консоль.
        self.last_error = ""

    def underway(self) -> bool:
        """Идёт ли прямо сейчас подъём показа."""
        with self._lock:
            return self._underway

    def take(self, args: list[str]) -> bool:
        """Взять поручение в работу; занято подъёмом - ``False``, и это отказ моста."""
        with self._lock:
            if self._underway:
                return False
            self._underway = True
            self.last_error = ""  # прошлый отказ живёт до начала следующего показа
        self._queue.put(args)
        return True

    def force(self, args: list[str]) -> bool:
        """Положить поручение, не спрашивая занятости; отвечает, шёл ли при этом подъём.

        Занятость тут не причина отказать, а факт, который зовущему нужно знать: пока
        главный поток досиживает чужой подъём, очередь до этого поручения не дойдёт, и
        снимать подъём приходится не ею (:meth:`hass.bridge.Bridge._stop`).
        """
        underway = self.underway()
        self._queue.put(args)
        return underway

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
        """Исполнить поручение и запомнить его отказ тем же словом, что и консоль."""
        try:
            result = command_result(self._command, args)
            if result.code:
                self.last_error = result.detail
        except Exception as error:
            self.last_error = why(error)
        finally:
            with self._lock:
                self._underway = False
