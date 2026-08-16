"""Хранилище настроек поверх ``/etc/torrcast/config.json``: читает их и пишет обратно.
Через него сценарий настройки ТВ меняет адрес приёмника, не зная про файл.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from torrcast.domain.settings import Settings


class ConfigFileStore:
    """Реализация порта настроек поверх прежних ``load_config`` и ``save_config``.

    🔴 Пишется не «то, что знает сценарий», а прежний конфиг с заменёнными полями:
    в файле лежат десятки ключей показа, которых сценарий не видит вовсе, и запись
    одного только своего среза стёрла бы их все.
    """

    def __init__(self, load: Callable[[], Any], save: Callable[[Any], None]) -> None:
        self._load = load
        self._save = save
        self._config: Any = None

    def load(self) -> Settings:
        self._config = self._load()
        return Settings(**self._shared(self._config))

    def save(self, settings: Settings) -> None:
        config = self._config if self._config is not None else self._load()
        for name in self._shared(config):
            setattr(config, name, getattr(settings, name))
        self._save(config)

    @staticmethod
    def _shared(config: Any) -> dict[str, Any]:
        """Поля, которые есть и у настроек сценария, и у файла конфига."""
        return {
            item.name: getattr(config, item.name)
            for item in fields(Settings)
            if hasattr(config, item.name)
        }
