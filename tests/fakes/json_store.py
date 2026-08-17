"""Хранит словарь JSON в памяти теста вместо файла на диске."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeJsonStore:
    """Битое хранилище изображается пустым словарём, как и отсутствующий файл."""

    raw: dict[str, Any] = field(default_factory=dict)
    writes: int = 0

    def read(self) -> dict[str, Any]:
        return dict(self.raw)

    def write(self, value: dict[str, Any]) -> None:
        self.writes += 1
        self.raw = dict(value)
