"""Совместимый фасад секундомера и часов показа.

Сам секундомер - файл и запись в него - живёт в
:mod:`torrcast.adapters.filesystem.stopwatch`, его лента таблицей - в
:mod:`torrcast.adapters.filesystem.stopwatch_report`, чистый разбор ленты - в
:mod:`torrcast.domain.report`, договор часов - в :mod:`torrcast.ports.clock`.
Отсюда их берут щупы и прежние импорты.
"""

from torrcast.adapters.filesystem.stopwatch import mark as mark
from torrcast.adapters.filesystem.stopwatch import read as read
from torrcast.adapters.filesystem.stopwatch_report import stopwatch_report as report
from torrcast.adapters.system_clock import CLOCK as CLOCK
from torrcast.adapters.system_clock import SystemClock as RealClock
from torrcast.domain.timeline_env import TIMELINE_ENV as TIMELINE_ENV
from torrcast.ports.clock import Clock as Clock

__all__ = ["CLOCK", "TIMELINE_ENV", "Clock", "RealClock", "mark", "read", "report"]
