"""Совместимый фасад сетевого поиска приёмников."""

import sys
from importlib import import_module

from torrcast.adapters.chromecast.scan import (
    CAST_PORT,
    Device,
    Found,
    Mdns,
    Net,
    alive,
    by_mdns,
    by_scan,
    find,
    hosts,
    interfaces,
    named,
    skipped,
    subnets,
)

__all__ = [
    "CAST_PORT",
    "Device",
    "Found",
    "Mdns",
    "Net",
    "alive",
    "by_mdns",
    "by_scan",
    "find",
    "hosts",
    "interfaces",
    "named",
    "skipped",
    "subnets",
]

_implementation = import_module("torrcast.adapters.chromecast.scan")
sys.modules[__name__] = _implementation
