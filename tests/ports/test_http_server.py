"""Проверяет контракт HTTP-сервера и поведение его фейка."""

from tests.fakes.http_server import FakeHttpServer
from torrcast.ports.http_server import HttpServer


def test_fake_records_server_lifecycle() -> None:
    fake = FakeHttpServer()
    port: HttpServer = fake
    assert port.start("/segments", 8080).base_url == "http://fake"
    port.stop()
    assert (fake.starts, fake.stop_count) == ([("/segments", 8080)], 1)
