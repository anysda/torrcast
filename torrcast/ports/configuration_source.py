"""Собирает неизменяемые настройки для сценариев."""

from typing import Protocol

from torrcast.domain.settings import Settings


class ConfigurationSource(Protocol):
    def load(self) -> Settings: ...
