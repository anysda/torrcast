"""Раздаёт подготовленное сценариями медиа по HTTP."""

from typing import Protocol

from torrcast.domain.server_address import ServerAddress


class HttpServer(Protocol):
    def start(self, directory: str, port: int) -> ServerAddress: ...
    def stop(self) -> None: ...
