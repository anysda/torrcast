"""Вид общего клиента Wikimedia для картинок: срочный у видимого списка, спокойный у полок."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.wiki.http_json_client import HttpJsonClient


class UrgentClient:
    """Те же запросы, помеченные как картинки: в коротком окне Википедии они раньше текстов.

    Срочный вид (видимый список) ещё и держит полку с прогревом справки, пока идут его
    запросы; спокойный (полки и карточка) стоит позади него, но впереди текстов карточек.
    Клиент без срочности (подделка пробы) проходит сквозь вид как есть.
    """

    def __init__(self, client: Any, urgent: bool = True) -> None:
        self.client = client
        self.urgent = urgent

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
            return self.client.get(
                host, path, params, headers, timeout, foreground, urgent=self.urgent, cover=True
            )
        return self.client.get(host, path, params, headers, timeout, foreground=foreground)

    def fetch(self, address: str, timeout: float) -> bytes:
        if isinstance(self.client, HttpJsonClient):
            return self.client.fetch(address, timeout, urgent=self.urgent)
        return bytes(self.client.fetch(address, timeout))

    def warm(self, host: str) -> None:
        self.client.warm(host)


__all__ = ["UrgentClient"]
