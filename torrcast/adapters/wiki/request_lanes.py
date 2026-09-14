"""Приоритетный доступ к полосам запросов одного хоста Wikimedia."""

import threading
import time
from typing import Final

#: Wikimedia accepts five simultaneous requests from CT501; the sixth returns 429.
#: The cap is per host: ru.wikipedia and query.wikidata.org answered 16 and 4 at once side by side.
REQUEST_LANES: Final = 5


class RequestLanes:
    """Пять полос, в которых клик обходит только ещё не начавшийся фон."""

    def __init__(self) -> None:
        self.active = 0
        self.waiting_foreground = 0
        self.condition = threading.Condition()

    def acquire(self, timeout: float, foreground: bool) -> bool:
        """Взять полосу, пропуская открывшуюся карточку перед фоновым хвостом.

        Уже начатый фон остаётся в сети. Но после его завершения следующий слот получает
        ждущий клик: фон не вправе занять его лишь потому, что первым проснулся после
        ``notify_all``. Очередь внутри каждого класса оставляет порядок ожидания ОС, а
        приоритет нужен только между классами.
        """
        deadline = time.monotonic() + timeout
        with self.condition:
            if foreground:
                self.waiting_foreground += 1
            try:
                while self.active >= REQUEST_LANES or (not foreground and self.waiting_foreground):
                    left = deadline - time.monotonic()
                    if left <= 0.0:
                        return False
                    self.condition.wait(left)
                self.active += 1
                return True
            finally:
                if foreground:
                    self.waiting_foreground -= 1
                    self.condition.notify_all()

    def release(self) -> None:
        """Освободить полосу и разбудить ожидающих более высокого класса."""
        with self.condition:
            self.active -= 1
            self.condition.notify_all()
