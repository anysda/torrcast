"""Читает построчные выгрузки справки с диска."""

from collections.abc import Iterator
from pathlib import Path


class TextFileSource:
    """Лениво читает UTF-8; отсутствующий файл выглядит пустым источником."""

    def lines(self, path: Path) -> Iterator[str]:
        try:
            with path.open(encoding="utf-8") as handle:
                yield from handle
        except OSError:
            return
