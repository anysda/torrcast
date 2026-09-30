"""Дождаться событий по именам под общим сроком: заявок приговора или байтов в пути."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable


def wait_each(
    lock: threading.Lock, events: dict[str, threading.Event], names: Iterable[str], limit: float
) -> None:
    """Дождаться событий тех имён, что ещё в ``events``, но не дольше ``limit`` на всех.

    Событие берётся под ``lock`` на каждое имя: пока ждали одно, другое могли снять.
    """
    deadline = time.monotonic() + limit
    for name in names:
        with lock:
            event = events.get(name)
        if event is not None:
            event.wait(max(0.0, deadline - time.monotonic()))
