"""Открывает подготовленный медиапоток через HTTP-порт."""

from dataclasses import dataclass

from torrcast.domain.server_address import ServerAddress
from torrcast.ports.http_server import HttpServer


@dataclass(slots=True)
class Feed:
    """Запускает раздачу каталога и возвращает её внешний адрес."""

    server: HttpServer

    def run(self, directory: str, port: int) -> ServerAddress:
        return self.server.start(directory, port)
