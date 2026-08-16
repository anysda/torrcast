"""Даёт сценарию doctor результаты системных проверок по порядку."""

from collections.abc import Iterable
from typing import Protocol

from torrcast.domain.settings import Settings

HealthLine = tuple[str, bool]


class HealthChecks(Protocol):
    """Проверяет внешнее окружение с уже загруженными настройками."""

    def check(self, settings: Settings) -> Iterable[HealthLine]: ...
