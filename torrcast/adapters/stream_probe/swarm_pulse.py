"""Признак жизни потока под ffprobe: тянет первые байты в фоне.

Зовёт его отбор релиза, чтобы не досиживать бюджет на молчащем рое."""

from __future__ import annotations

import contextlib
import threading
import time
import urllib.request
from typing import TYPE_CHECKING, Any

from torrcast.domain.warm_open import HEAD_WARM, WARM_TIMEOUT

if TYPE_CHECKING:
    from collections.abc import Callable

    ContactWait = Any


def swarm_pulse(
    source_url: str, grace: float, wait: ContactWait | None = None
) -> Callable[[], bool]:
    """Признак жизни потока под ffprobe: тянет первые байты в фоне и отвечает, стоит ли
    ещё ждать. Пришёл хоть байт — раздача жива и читается (у «Моаны 2» заголовок едет
    17 с, это норма, и обрывать её нельзя). Ни байта за ``grace`` — рой молчит: пиров
    нет, и досиживать на нём весь :data:`torrcast.cli.PROBE_BUDGET` незачем, запасной уже
    греется параллельно (:meth:`torrcast.cli._Bench.resolve`).

    Читаем ровно до первого куска: подтвердить жизнь достаточно, а сами байты в кэш роя
    тянут прогрев (:func:`warm_file`) и показ — второй раз их брать незачем.
    """
    started = time.monotonic()
    seen = threading.Event()

    def pull() -> None:
        request = urllib.request.Request(source_url, headers={"Range": f"bytes=0-{HEAD_WARM - 1}"})
        with (
            contextlib.suppress(Exception),
            urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer,
        ):
            if answer.read(1 << 20):
                seen.set()

    threading.Thread(target=pull, daemon=True).start()

    def alive() -> bool:
        began = wait.activated_at if wait is not None else started
        return seen.is_set() or began is None or (time.monotonic() - began) < grace

    return alive
