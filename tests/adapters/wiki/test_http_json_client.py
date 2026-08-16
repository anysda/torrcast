"""Проверяет устройство HTTPS-клиента Wikimedia без обращения в сеть."""

from torrcast.adapters.wiki.http_json_client import HttpJsonClient


def test_keeps_user_agent() -> None:
    """Клиент хранит переданное имя автоматики для каждого запроса."""
    assert HttpJsonClient("torrcast/test").user_agent == "torrcast/test"
