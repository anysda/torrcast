"""Дожидается фонового добавления magnet через часы порта."""

import threading
from dataclasses import dataclass

from torrcast.domain.infra_error import InfraError
from torrcast.ports.clock import Clock


@dataclass(slots=True)
class Warmup:
    """Фоновое добавление magnet в TorrServer под меню."""

    magnet: str
    clock: Clock
    torrent_hash: str = ""
    error: InfraError | None = None
    thread: threading.Thread | None = None

    def result(self, timeout: float = 30.0) -> str:
        """Дождаться hash прогретой раздачи."""
        deadline = self.clock.monotonic() + timeout
        while self.thread is not None and self.thread.is_alive():
            left = deadline - self.clock.monotonic()
            if left <= 0:
                break
            self.clock.sleep(min(0.01, left))
        if self.error is not None:
            raise self.error
        if not self.torrent_hash:
            raise InfraError("TorrServer не принял раздачу за отведённое время")
        return self.torrent_hash
