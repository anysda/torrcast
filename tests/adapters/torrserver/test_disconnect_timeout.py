"""Срок закрытия раздачи без читателей читается из настроек TorrServer один раз."""

from __future__ import annotations

from torrcast.adapters.torrserver.disconnect_timeout import disconnect_timeout
from torrcast.domain.server_down_error import ServerDownError


def test_the_disconnect_timeout_is_read_once_and_falls_back_to_thirty() -> None:
    """Настройки читаются один раз; не прочитались или ноль - умолчание TorrServer 30 с."""
    calls: list[str] = []

    def post(path: str, body: dict[str, object]) -> object:
        calls.append(path)
        return {"TorrentDisconnectTimeout": 45}

    def down(path: str, body: dict[str, object]) -> object:
        raise ServerDownError("молчит")

    def zero(path: str, body: dict[str, object]) -> object:
        return {"TorrentDisconnectTimeout": 0}

    assert disconnect_timeout("http://ts-keep-a", post) == 45.0
    assert disconnect_timeout("http://ts-keep-a", post) == 45.0 and calls == ["/settings"]
    assert disconnect_timeout("http://ts-keep-b", down) == 30.0
    assert disconnect_timeout("http://ts-keep-c", zero) == 30.0
