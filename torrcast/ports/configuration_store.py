"""Читает и сохраняет настройки команды configure."""

from typing import Protocol

from torrcast.domain.settings import Settings


class ConfigurationStore(Protocol):
    def load(self) -> Settings: ...
    def save(self, settings: Settings) -> None: ...
