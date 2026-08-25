"""Каждый отданный сегмент - в недельный след: номер, вес, время, ожидание, ИСТОЧНИК.

Зовёт его раздача (:class:`torrcast.adapters.http_server._handler._Handler`)."""

from __future__ import annotations

import time

from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.ports.journal.slot import journal


def log_segment(name: str, began: float, size: int, took: float, src: str) -> None:
    """Записать в след один отданный приёмнику сегмент; манифест сегментом не считается.

    Источник (``src``) - живая упаковка или прогретое. Без него в ленте не видно
    главного: показ идёт кусками ДВУХ производителей, и разбор «почему приёмник
    споткнулся вот здесь» упирался в то, что по записи нельзя сказать, чей это был
    кусок и не сменился ли производитель ровно на этом месте.

    🔴 Это горячий путь. :func:`torrcast.adapters.filesystem.trace_journal.emit`
    только кладёт запись в очередь - ни ``open``, ни ``write``, ни ``flush`` тут не
    случается, показ не ждёт журнал.
    Отдельно от ``TORRCAST_TRACE`` (:meth:`_Handler._sent`): тот пишет в консоль по
    требованию, а след ведётся всегда. Манифест не пишем - он не сегмент и дёргается на
    каждый опрос.
    """
    if not name.endswith((".ts", ".m4s")):
        return

    journal().segment(
        slot=segment_slot(name),
        mb=size / 1e6,
        sent=took,
        wait=time.monotonic() - began - took,
        src=src,
    )
