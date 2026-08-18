"""Совместимый фасад команды показа."""

# ruff: noqa: F403, F405
import sys

from torrcast import trace as trace
from torrcast.usecases import cast_command as _implementation
from torrcast.usecases.cast_command import *

__all__ = [
    "_cmd_play",
    "_configure_cast_command",
    "trace",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
