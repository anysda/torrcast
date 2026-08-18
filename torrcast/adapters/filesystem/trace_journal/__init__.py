"""Недельный диагностический след: один структурированный ``jsonl`` рядом с состоянием.

Зачем отдельный слой, а не ещё один ``print``: то, что нужно для разбора сеанса, уже
пишется, но врозь и недолго. Фазы старта живут в секундомере
(:func:`torrcast.adapters.filesystem.stopwatch.mark`),
время отдачи кусков - в ``TORRCAST_TRACE`` (:meth:`torrcast.stream._Handler._sent`), решения
отбора - в журнале прогресса (:meth:`torrcast.console.Progress.note`) и в ``journald`` юнита
показа. Каждое из этого гаснет вместе с командой и по нему нельзя спросить «что было за
неделю». Этот слой ничего из перечисленного не дублирует: он сводит те же события в одну
ленту - :func:`mark` и :func:`~torrcast.console.Progress.note` дозывают :func:`emit` сами,
- и держит её семь дней с потолком места.

🔴 **Запись не в горячем пути.** Отдача сегмента (:meth:`torrcast.stream._Handler._serve`)
зовёт :func:`emit`, а он только кладёт запись в очередь без единого обращения к диску:
пишет её на диск отдельный фоновый поток (:class:`_Writer`). Показ не ждёт ни ``open``, ни
``write``, ни ``flush`` - это проверяется тестом (``tests/test_trace.py``).

Всё локально: лента лежит там же, где состояние, никакой внешней системы. Разбор - команда
``cast log`` (:func:`digest`), она же читает :func:`records`.

🔴 **Слепая зона ленты.** Плата за то, что показ не ждёт диск, - конечная очередь: когда
фоновый писатель отстаёт, запись роняется (:meth:`_Writer.put`). Молча это больше не
происходит - потери считаются и уходят в ленту записью ``lost``, и ``cast log`` её печатает,
- но САМИ потерянные события не восстановимы. Читать ленту рядом с такой записью надо с
поправкой: пропуск там значит «съедено очередью», а не «этого не было».

**Схема событий - это файлы рядом.** Имена полей живут в них, а не по местам вызова: место
вызова знает свои числа, а как они называются в ленте и как читаются в ``cast log`` - дело
этого пакета. Каждый такой файл (:func:`nudge`, :func:`segment`, :func:`plan`,
:func:`reload`, :func:`offline`, :func:`resupply`, :func:`dark`, :func:`revive`,
:func:`seek`, :func:`evict`, :func:`skew`, :func:`warmth`) - это и объявление полей, и
единственный способ их поставить; печать той же записи лежит в :func:`digest`. Все они, как
и :func:`emit`, только кладут запись в очередь: ни одна не имеет права ждать диск, даже
если зовут её не из горячего пути.
"""

from torrcast.adapters.filesystem.trace_journal.dark import dark
from torrcast.adapters.filesystem.trace_journal.emit import emit
from torrcast.adapters.filesystem.trace_journal.evict import evict
from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal as FileJournal
from torrcast.adapters.filesystem.trace_journal.health import health
from torrcast.adapters.filesystem.trace_journal.log_dir import LOG_ENV, log_dir
from torrcast.adapters.filesystem.trace_journal.log_path import log_path
from torrcast.adapters.filesystem.trace_journal.nudge import nudge
from torrcast.adapters.filesystem.trace_journal.offline import offline as offline
from torrcast.adapters.filesystem.trace_journal.plan import plan
from torrcast.adapters.filesystem.trace_journal.prune import MAX_BYTES as MAX_BYTES
from torrcast.adapters.filesystem.trace_journal.prune import RETAIN_DAYS as RETAIN_DAYS
from torrcast.adapters.filesystem.trace_journal.records import records
from torrcast.adapters.filesystem.trace_journal.reload import reload
from torrcast.adapters.filesystem.trace_journal.resupply import resupply as resupply
from torrcast.adapters.filesystem.trace_journal.revive import revive
from torrcast.adapters.filesystem.trace_journal.seek import seek
from torrcast.adapters.filesystem.trace_journal.segment import segment
from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV, session_id
from torrcast.adapters.filesystem.trace_journal.shutdown import shutdown
from torrcast.adapters.filesystem.trace_journal.skew import skew
from torrcast.adapters.filesystem.trace_journal.start_session import start_session
from torrcast.adapters.filesystem.trace_journal.warmth import warmth
from torrcast.domain.digest import digest

__all__ = [
    "LOG_ENV",
    "SID_ENV",
    "dark",
    "digest",
    "emit",
    "evict",
    "health",
    "log_dir",
    "log_path",
    "nudge",
    "plan",
    "records",
    "reload",
    "revive",
    "seek",
    "segment",
    "session_id",
    "shutdown",
    "skew",
    "start_session",
    "warmth",
]
