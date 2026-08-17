"""Поля записи ``play/segment``: отданный приёмнику кусок и его производитель.

Зовёт её горячий путь отдачи сегмента, читает разбор ``cast log``."""

from __future__ import annotations

from torrcast.adapters.filesystem.trace_journal.emit import emit


def segment(slot: int, mb: float, sent: float, wait: float, src: str) -> None:
    """Отданный приёмнику кусок: номер, вес, время отдачи, ожидание и ИСТОЧНИК.

    ``src`` - :data:`PACKED` или :data:`WARMED`. Без него в ленте не отличить кусок живой
    упаковки от прогретого, а это разные производители: разойдись у них решение о
    кодировании - и на стыке декодер приёмника переинициализируется. Стыки считает
    :func:`digest`, поэтому поле стоит в каждой записи, а не только на переходах: по одним
    переходам нельзя сказать, чем шёл показ между ними.

    🔴 Зовётся из горячего пути отдачи (:meth:`torrcast.stream._Handler._log_segment`):
    только :func:`emit`, то есть только укладка в очередь.
    """
    emit(
        "play",
        "segment",
        slot=slot,
        mb=round(mb, 2),
        sent=round(sent, 3),
        wait=round(wait, 3),
        src=src,
    )
