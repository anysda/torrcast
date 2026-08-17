"""Совместимый фасад секундомера и часов показа.

Сам секундомер - файл и запись в него - живёт в
:mod:`torrcast.adapters.filesystem.stopwatch`, разбор его ленты в таблицу - в
:mod:`torrcast.domain.report`, договор часов - в :mod:`torrcast.ports.clock`.
Отсюда их берут щупы и прежние импорты.
"""

from pathlib import Path

from torrcast.adapters.filesystem.stopwatch import mark as mark
from torrcast.adapters.filesystem.stopwatch import read as read
from torrcast.adapters.system_clock import SystemClock as RealClock
from torrcast.domain.report import report as _report
from torrcast.domain.timeline_env import TIMELINE_ENV as TIMELINE_ENV
from torrcast.ports.clock import Clock as Clock

__all__ = ["CLOCK", "TIMELINE_ENV", "Clock", "RealClock", "mark", "read", "report"]

#: Часы боевого пути. Заводить свои незачем - объект без состояния.
CLOCK: Clock = RealClock()


def report(path: str | Path, zero: str = "") -> str:
    """Лента меток из файла как таблица: прежний вызов щупов одной строкой."""
    return _report(read(path), zero)
