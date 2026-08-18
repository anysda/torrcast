"""Хранит JSON-объект во внешнем постоянном хранилище."""

from typing import Protocol

from torrcast.ports.json_value import JsonValue


class JsonStore(Protocol):
    """Читает и целиком заменяет словарь JSON."""

    def read(self) -> dict[str, JsonValue]: ...

    def write(self, value: dict[str, JsonValue]) -> None: ...
