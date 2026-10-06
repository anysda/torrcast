"""Нить опроса приёмника ТВ, которой живёт каст (:class:`web.tv_session.TvSession`).

Нить одна на связь: новая заводится только после того, как прежняя погашена, а гасится
она раньше, чем кто-то тронет приёмник.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class TvPoll:
    """Держит нить опроса и её флаг остановки между :meth:`arm` и :meth:`disarm`."""

    _stop: threading.Event | None = field(default=None, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def arm(self, pump: Callable[[threading.Event], None]) -> None:
        """Завести опрос: держит место у pychromecast свежим, пока каст живёт."""
        stop = threading.Event()
        thread = threading.Thread(target=pump, args=(stop,), daemon=True)
        self._stop, self._thread = stop, thread
        thread.start()

    def disarm(self, seconds: float) -> None:
        """Остановить опрос и дождаться его конца перед тем, как трогать приёмник."""
        if self._stop is not None:
            self._stop.set()
        # Опрос, снимающий каст сам (:meth:`TvSession._pump`), себя не ждёт: join себя - ошибка.
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=seconds)
        self._stop = self._thread = None
