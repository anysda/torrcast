"""Сверка базы TorrServer с рядом «Продолжить» фоном (:func:`web.record_sweep.record_sweep`)."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.ports.state_store.slot import store
from torrcast.usecases.torrents import _held_by_show
from web.record_sweep import record_sweep
from web.record_warm import _showing

#: Терпение одного запроса к службе: уборка идёт фоном и висеть не должна.
TIMEOUT: Final = 10.0


def _sweep_records(base_url: str) -> bool:
    """Одна сверка; правда - она прошла вся, а не уступила показу, держателю или молчанию."""
    if _showing():
        return False
    with contextlib.suppress(TorrcastError):
        engine = TorrServer(base_url, timeout=TIMEOUT)
        gone, whole = record_sweep(engine, store().load().entries, _held_by_show)
        if gone:
            journal().mark("уборка записей", снесено=len(gone))
        return whole
    return False


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="torrcast-record-sweep", daemon=True).start()


@dataclass
class SweepLater:
    """Сверка фоном по одной за раз; ряд считается убранным, только когда сверка прошла.

    Пропущенная или оборванная (идёт показ, служба молчит или не сносит, держатель ждал
    замка) не теряется: следующее касание того же ряда зовёт её снова. Зовут касание ряда
    (:mod:`web.record_hold`) и старт службы.
    """

    spawn: Callable[[Callable[[], None]], None] = _thread
    _done: tuple[str, ...] | None = field(default=None, repr=False)
    _busy: bool = field(default=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __call__(self, base_url: str, row: tuple[str, ...] = ()) -> None:
        """Сверить базу службы под ряд ``row``, если он ещё не убран и сверка не идёт."""
        with self._lock:
            if self._busy or row == self._done:
                return
            self._busy = True
        self.spawn(lambda: self._run(base_url, row))

    def _run(self, base_url: str, row: tuple[str, ...]) -> None:
        swept = False
        try:
            swept = _sweep_records(base_url)
        finally:
            with self._lock:
                self._busy = False
                if swept:
                    self._done = row


#: Сверка процесса: касания всех вкладок и старт службы идут через одну, не наперегонки.
SWEEP_LATER: Final = SweepLater()
