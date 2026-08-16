"""Минимальный интерфейс торрент-файла для правил эпизодов."""

from typing import Protocol

__all__ = ["FileLike"]


class FileLike(Protocol):
    """Файл раздачи глазами чистого парсера эпизодов."""

    @property
    def index(self) -> int: ...

    @property
    def name(self) -> str: ...

    @property
    def size(self) -> int: ...
