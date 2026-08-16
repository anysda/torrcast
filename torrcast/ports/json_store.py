"""Хранит JSON-объект во внешнем постоянном хранилище."""

from typing import Any, Protocol


class JsonStore(Protocol):
    """Читает и целиком заменяет словарь JSON."""

    def read(self) -> dict[str, Any]: ...

    def write(self, value: dict[str, Any]) -> None: ...
