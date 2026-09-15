"""Вид общего клиента Wikimedia для видимого списка: его запросы идут впереди фона."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.wiki.http_json_client import HttpJsonClient


class UrgentClient:
    """Те же запросы, но срочные: полка и прогрев справки ждут, пока идут они.

    Клиент без срочности (подделка пробы) проходит сквозь вид как есть.
    """

    def __init__(self, client: Any) -> None:
        self.client = client

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
        foreground: bool = False,
    ) -> Any:
        if isinstance(self.client, HttpJsonClient):
            return self.client.get(host, path, params, headers, timeout, foreground, urgent=True)
        return self.client.get(host, path, params, headers, timeout, foreground=foreground)

    def fetch(self, address: str, timeout: float) -> bytes:
        if isinstance(self.client, HttpJsonClient):
            return self.client.fetch(address, timeout, urgent=True)
        return bytes(self.client.fetch(address, timeout))

    def warm(self, host: str) -> None:
        self.client.warm(host)


__all__ = ["UrgentClient"]
