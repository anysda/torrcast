"""Совместимый фасад оживления показа."""

# ruff: noqa: F403, F405, RUF022

import sys

from torrcast import _playback_revival_impl as _implementation
from torrcast._playback_revival_impl import *
from torrcast._playback_revival_impl import _hold, _Revival

__all__ = [
    "CAUTIOUS",
    "CLOCK",
    "Clock",
    "ENDING_RATIO",
    "Feed",
    "InfraError",
    "Profile",
    "REVIVE_DROP",
    "REVIVE_LIMIT",
    "REVIVE_LIVED",
    "REVIVE_PAUSE",
    "REVIVE_TRIES",
    "Receiver",
    "Supply",
    "TAIL_LIMIT",
    "TYPE_CHECKING",
    "Warmer",
    "_Revival",
    "_hold",
    "dataclass",
    "mark_playing",
    "os",
    "time",
    "trace",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
