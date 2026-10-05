"""Замок выкладки, занятый параллельным проходом: гонка TC-1405 без сна и без лотереи.

Параллельный проход (:func:`torrcast.usecases.feed_pack.feed_sweep._sweep`) держит
настоящий замок в своём потоке и отпускает его ровно тогда, когда кто-то встал его
ждать. Кто замок не ждёт, а уходит ни с чем, - уходит всегда, а не через раз.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.packer import Packer


class Contended:
    """Замок, который держит чужой проход; ``on_refused`` - что случится в миг отказа."""

    def __init__(self, on_refused: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._free = threading.Event()
        self._on_refused = on_refused
        self.waited = threading.Event()
        self.refused = 0
        held = threading.Event()
        self._pass = threading.Thread(target=self._hold, args=(held,), daemon=True)
        self._pass.start()
        held.wait()

    def _hold(self, held: threading.Event) -> None:
        with self._lock:
            held.set()
            self._free.wait()  # проход идёт, пока его никто не ждёт

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if blocking:
            self.waited.set()
            self._free.set()
            return self._lock.acquire(True, timeout)
        if self._lock.acquire(False):
            return True
        self.refused += 1
        if self._on_refused is not None:
            self._on_refused()
        return False

    def release(self) -> None:
        self._lock.release()

    def close(self) -> None:
        """Отпустить проход, если его так никто и не дождался: поток не висит после теста."""
        self._free.set()
        self._pass.join()


def contend(run: Packer, on_refused: Callable[[], None] | None = None) -> Contended:
    """Поставить прогону замок выкладки, занятый параллельным проходом."""
    lock = Contended(on_refused)
    run.publish_lock = cast("threading.Lock", lock)
    return lock
