"""Запрашивает JSON у внешнего HTTP-источника."""

from typing import Any, Protocol


class JsonClient(Protocol):
    """Выполняет один GET-запрос с заданным таймаутом."""

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> Any: ...
