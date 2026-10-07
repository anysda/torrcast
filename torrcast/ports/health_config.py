"""Настройки в том объёме, который нужен самопроверке окружения.

Узкий протокол вместо файлового конфига: сценарий :mod:`torrcast.usecases.doctor` не
знает, откуда взялись эти семь значений, а старый ``Config`` подходит сюда как есть.
"""

from typing import Protocol


class HealthConfig(Protocol):
    """Только те ключи, о которых спрашивает ``cast doctor``."""

    @property
    def tv(self) -> str | None: ...
    @property
    def receiver(self) -> str: ...
    @property
    def transport(self) -> str: ...
    @property
    def hls_cert(self) -> str: ...
    @property
    def prowlarr_url(self) -> str: ...
    @property
    def prowlarr_apikey(self) -> str: ...
    @property
    def torrserver_url(self) -> str: ...
