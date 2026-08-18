"""Запрашивает JSON у внешнего HTTP-источника."""

from typing import Protocol

from torrcast.ports.json_value import JsonValue


class JsonClient(Protocol):
    """Выполняет один GET-запрос с заданным таймаутом."""

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> JsonValue: ...
