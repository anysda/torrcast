"""Совместимый фасад терминальной консоли."""

import sys
from importlib import import_module

from torrcast.adapters.console.console import (
    Progress,
    ask,
    ask_line,
    clean,
    iutf8,
    stdin_is_tty,
    terminal,
)

__all__ = ["Progress", "ask", "ask_line", "clean", "iutf8", "stdin_is_tty", "terminal"]

_implementation = import_module("torrcast.adapters.console.console")
sys.modules[__name__] = _implementation
