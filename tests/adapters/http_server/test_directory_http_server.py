"""Проверяет безопасную остановку ещё не запущенного сервера."""

from torrcast.adapters.http_server.directory_http_server import DirectoryHttpServer


def test_stop_before_start_is_noop() -> None:
    DirectoryHttpServer().stop()
