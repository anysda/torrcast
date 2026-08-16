"""Изображает для тестов раздачу подготовленного медиа."""

from dataclasses import dataclass, field

from torrcast.domain.server_address import ServerAddress


@dataclass
class FakeHttpServer:
    address: ServerAddress = field(default_factory=lambda: ServerAddress("http://fake"))
    starts: list[tuple[str, int]] = field(default_factory=list)
    stop_count: int = 0

    def start(self, directory: str, port: int) -> ServerAddress:
        self.starts.append((directory, port))
        return self.address

    def stop(self) -> None:
        self.stop_count += 1
