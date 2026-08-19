"""Лента за портом журнала: тот же файл и тот же фоновый писатель, но объектом.

Заводит его композиционный корень (:mod:`torrcast.runtime.wire`) и раздаёт слоям."""

from __future__ import annotations

from torrcast.adapters.filesystem.stopwatch.mark import mark as _mark
from torrcast.adapters.filesystem.trace_journal.dark import dark
from torrcast.adapters.filesystem.trace_journal.emit import emit
from torrcast.adapters.filesystem.trace_journal.evict import evict
from torrcast.adapters.filesystem.trace_journal.health import health
from torrcast.adapters.filesystem.trace_journal.nudge import nudge
from torrcast.adapters.filesystem.trace_journal.offline import offline
from torrcast.adapters.filesystem.trace_journal.plan import plan
from torrcast.adapters.filesystem.trace_journal.records import records
from torrcast.adapters.filesystem.trace_journal.reload import reload
from torrcast.adapters.filesystem.trace_journal.resupply import resupply
from torrcast.adapters.filesystem.trace_journal.revive import revive
from torrcast.adapters.filesystem.trace_journal.seek import seek
from torrcast.adapters.filesystem.trace_journal.segment import segment
from torrcast.adapters.filesystem.trace_journal.session_id import session_id
from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown
from torrcast.adapters.filesystem.trace_journal.skew import skew
from torrcast.adapters.filesystem.trace_journal.start_session import start_session
from torrcast.adapters.filesystem.trace_journal.warmth import warmth


class FileJournal:
    """Лента как объект: тот же файл и тот же фоновый писатель, но за портом.

    Модульные функции рядом остаются на месте - их зовут щупы и тесты ленты, - а слои
    получают этот объект от композиционного корня
    (:mod:`torrcast.runtime.wire`) и знают только договор :class:`~torrcast.ports.
    journal.Journal`.
    """

    emit = staticmethod(emit)
    mark = staticmethod(_mark)
    shutdown = staticmethod(shutdown)
    records = staticmethod(records)
    session_id = staticmethod(session_id)
    start_session = staticmethod(start_session)
    health = staticmethod(health)
    nudge = staticmethod(nudge)
    segment = staticmethod(segment)
    plan = staticmethod(plan)
    reload = staticmethod(reload)
    offline = staticmethod(offline)
    resupply = staticmethod(resupply)
    dark = staticmethod(dark)
    revive = staticmethod(revive)
    seek = staticmethod(seek)
    evict = staticmethod(evict)
    skew = staticmethod(skew)
    warmth = staticmethod(warmth)
