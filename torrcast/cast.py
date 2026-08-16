"""Совместимый фасад живого приёмника Chromecast."""

import sys
from importlib import import_module

from torrcast.adapters.chromecast.cast import (
    HLS_HINTS,
    HLS_TYPE,
    ChromecastReceiver,
    hush_cosmetic_noise,
    make_receiver,
)
from torrcast.cast_core import NOT_RAISED, Position, Receiver, StartRefusedError, trust_anchor
from torrcast.cast_mock import MockReceiver, Report

__all__ = [
    "HLS_HINTS",
    "HLS_TYPE",
    "NOT_RAISED",
    "ChromecastReceiver",
    "MockReceiver",
    "Position",
    "Receiver",
    "Report",
    "StartRefusedError",
    "hush_cosmetic_noise",
    "make_receiver",
    "trust_anchor",
]

_implementation = import_module("torrcast.adapters.chromecast.cast")
sys.modules[__name__] = _implementation
