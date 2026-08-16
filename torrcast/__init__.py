"""Публичный API torrcast: версия и реэкспорт ошибок."""

from typing import Any

from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.version import __version__
from torrcast.domain.why import why

# Аннотации сохраняют прежний типовой API без файлов-обёрток.
commands_legacy: Any
doctor_checks: Any

__all__ = [
    "InfraError",
    "NotFoundError",
    "SwarmError",
    "TorrcastError",
    "__version__",
    "why",
]
