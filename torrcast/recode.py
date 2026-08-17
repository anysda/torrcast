"""Совместимый фасад адаптера перекодирования."""

# ruff: noqa: F403, F405

import sys

from torrcast.adapters import recode as _implementation
from torrcast.adapters.recode import *

__all__ = [
    "DEADLINE_MARGIN",
    "FIT_FLOOR",
    "FIT_SLACK",
    "FULL_FLOOR",
    "FULL_GAIN",
    "FULL_PRESET",
    "HEAD_LIMIT",
    "HEAD_NICE",
    "MAXRATE_GAIN",
    "NEIGHBOUR_TOLL",
    "NICE",
    "PACE_MEMORY",
    "PASSPORT_WEIGHT",
    "PRESETS",
    "REALTIME",
    "RECODE_DIR",
    "RECODE_HEIGHT",
    "RUN_MAX",
    "SHRINK_FRESH",
    "TONEMAP",
    "VBV_SECONDS",
    "Encode",
    "Pace",
    "Recoder",
    "Weights",
    "level_for",
    "preset_for",
    "whole_encode",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
