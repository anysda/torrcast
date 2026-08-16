"""Совместимый фасад адаптера перекодирования."""

# ruff: noqa: F403, F405

import sys

from torrcast.adapters import recode as _implementation
from torrcast.adapters.recode import *

HEAD_LIMIT = _implementation.HEAD_LIMIT
REALTIME = _implementation.REALTIME
SHRINK_FRESH = _implementation.SHRINK_FRESH
TONEMAP = _implementation.TONEMAP
level_for = _implementation.level_for

__all__ = [
    "DEADLINE_MARGIN",
    "FIT_FLOOR",
    "FIT_SLACK",
    "FULL_FLOOR",
    "FULL_GAIN",
    "FULL_PRESET",
    "MAXRATE_GAIN",
    "NEIGHBOUR_TOLL",
    "PRESETS",
    "RECODE_DIR",
    "RECODE_HEIGHT",
    "VBV_SECONDS",
    "Encode",
    "Pace",
    "Recoder",
    "Weights",
    "preset_for",
    "whole_encode",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
