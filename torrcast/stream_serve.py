"""Совместимый фасад внешней части медиатракта."""

# ruff: noqa: F403, F405

import sys
from importlib import import_module

from torrcast.adapters.http_server.stream_serve import *

__all__ = [
    "TRACE",
    "TYPE_CHECKING",
    "_ASSET_RE",
    "_RANGE_RE",
    "_TYPES",
    "_UNIT_NAME",
    "Any",
    "ClassVar",
    "Final",
    "HlsServer",
    "InfraError",
    "Path",
    "_Handler",
    "_Server",
    "_opt_str",
    "_scope",
    "_systemd",
    "contextlib",
    "hls_base",
    "http",
    "json",
    "os",
    "our_address",
    "re",
    "socket",
    "ssl",
    "start_play_unit",
    "stop_play_unit",
    "subprocess",
    "sys",
    "threading",
    "time",
    "unit_active",
    "unit_key",
    "unit_why",
    "why",
]

_implementation = import_module("torrcast.adapters.http_server.stream_serve")
sys.modules[__name__] = _implementation
