"""Сверка базы TorrServer с рядом «Продолжить» фоном (:func:`web.record_sweep.record_sweep`)."""

from __future__ import annotations

import contextlib
import threading
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


def _sweep_records(base_url: str) -> None:
    """Сверить базу службы с рядом; идёт показ - ничего не трогать до следующего раза."""
    if _showing():
        return
    with contextlib.suppress(TorrcastError):
        gone = record_sweep(
            TorrServer(base_url, timeout=TIMEOUT), store().load().entries, _held_by_show
        )
        if gone:
            journal().mark("уборка записей", снесено=len(gone))


def sweep_later(base_url: str) -> None:
    """:func:`_sweep_records` фоном: зовут её касание ряда и старт службы."""
    threading.Thread(
        target=_sweep_records, args=(base_url,), name="torrcast-record-sweep", daemon=True
    ).start()
