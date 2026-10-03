"""Хранит отсрочку первого контакта с роем на часах порта."""

import threading

from torrcast.adapters.system_clock import CLOCK
from torrcast.ports.clock import Clock


class ContactWait(float):
    """Отсрочка первого контакта, часы которой запускает выбор релиза."""

    _seconds: float
    _activated_at: float | None
    _lock: threading.Lock
    _clock: Clock

    def __new__(cls, seconds: float, clock: Clock | None = None) -> "ContactWait":
        wait = super().__new__(cls, seconds)
        wait._seconds = seconds
        wait._activated_at = None
        wait._lock = threading.Lock()
        wait._clock = clock or CLOCK
        return wait

    @property
    def activated_at(self) -> float | None:
        return self._activated_at

    @property
    def seconds(self) -> float:
        return self._seconds

    def activate(self, seconds: float) -> None:
        with self._lock:
            if self._activated_at is None:
                self._seconds = seconds
                self._activated_at = self._clock.monotonic()
