"""Проверяет сценарий раздачи потока на фейковом сервере."""

from tests.fakes.http_server import FakeHttpServer
from torrcast.domain.server_address import ServerAddress
from torrcast.usecases.feed import Feed


def test_feed_starts_server_and_returns_address() -> None:
    server = FakeHttpServer(ServerAddress("http://tv/media"))

    address = Feed(server).run("/run/torrcast", 8090)

    assert address == ServerAddress("http://tv/media")
    assert server.starts == [("/run/torrcast", 8090)]
