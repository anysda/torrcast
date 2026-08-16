"""Совместимый фасад самопроверки окружения ``cast doctor``.

Здесь же композиция: сценарий :mod:`torrcast.usecases.doctor` получает системную среду,
а старое имя модуля продолжает отвечать на прежние вопросы.
"""

# ruff: noqa: I001

import sys
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutor

from torrcast.adapters.chromecast.scan import CAST_PORT
from torrcast.adapters.health.system_health_environment import SystemHealthEnvironment
from torrcast.usecases import doctor as _implementation
from torrcast.usecases.doctor import (
    CACHE_DISK_RESERVE as CACHE_DISK_RESERVE,
    Doctor as Doctor,
    IPV4_ONLY as IPV4_ONLY,
    KEY_INDEXER as KEY_INDEXER,
    Line as Line,
    _INDEXER_TIMEOUT as _INDEXER_TIMEOUT,
    _TIMEOUT as _TIMEOUT,
    _cache as _cache,
    _enabled_names as _enabled_names,
    _family as _family,
    _json as _json,
    _live_indexers as _live_indexers,
    _mdns as _mdns,
    _probe_indexer as _probe_indexer,
    _prowlarr as _prowlarr,
    _settings as _settings,
    _trace as _trace,
    checkup as checkup,
    disk_free as disk_free,
    machine_memory as machine_memory,
)

__all__ = ["CAST_PORT", "checkup"]

_implementation._configure(SystemHealthEnvironment())

# Старые имена остаются только как уже загруженные модули, без плоских файлов-сирот.
sys.modules.setdefault("torrcast.doctor_checks", _implementation)
sys.modules[__name__] = _implementation
