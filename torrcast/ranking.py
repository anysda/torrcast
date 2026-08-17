"""Совместимый фасад правил ранжирования."""

import sys

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.usecases import rank as _implementation
from torrcast.usecases.rank import *  # noqa: F403
from torrcast.usecases.rank import default_unnamed as default_unnamed

__all__ = _implementation.__all__

_implementation.configure(PrintConsole())

sys.modules[__name__] = _implementation
