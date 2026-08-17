"""Откуда взялся отданный приёмнику кусок: живая упаковка или прогретое.

Имена короткие, потому что поле идёт в КАЖДОЙ записи сегмента. Пишет их сама лента
(:mod:`torrcast.adapters.filesystem.trace_journal`), читает разбор
(:mod:`torrcast.domain.digest`).
"""

from typing import Final

PACKED: Final = "pack"
WARMED: Final = "warm"
