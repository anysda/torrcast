"""Читает строки из внешнего текстового источника."""

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol


class TextSource(Protocol):
    """Возвращает строки UTF-8 или пустой источник при недоступности."""

    def lines(self, path: Path) -> Iterable[str]: ...
