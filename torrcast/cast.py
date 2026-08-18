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
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.position import Position
from torrcast.domain.reception_report import ReceptionReport as Report
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.trust_anchor import trust_anchor
from torrcast.ports.receiver import Receiver

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
