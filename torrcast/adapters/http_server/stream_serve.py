"""Прежнее имя внешней части медиатракта: собирает раздачу и команды юнита показа.

Сами единицы разъехались по соседним модулям; отсюда их берёт всё, что звало внешнюю
часть медиатракта одним именем.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final

from torrcast.adapters.http_server._handler import (
    _ASSET_RE,
    _RANGE_RE,
    _TYPES,
    _Handler,
    _tracing,
)
from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.adapters.http_server.hls_server import HlsServer, _Server
from torrcast.adapters.http_server.our_address import our_address
from torrcast.adapters.systemd._systemd_call import _scope, _systemd
from torrcast.adapters.systemd.start_play_unit import start_play_unit
from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.adapters.systemd.unit_active import unit_active
from torrcast.adapters.systemd.unit_key import unit_key
from torrcast.adapters.systemd.unit_why import unit_why
from torrcast.domain.infra_error import InfraError
from torrcast.domain.unit_naming import _UNIT_NAME
from torrcast.domain.why import why

__all__ = [
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
    "_tracing",
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


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
