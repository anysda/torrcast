"""Отдаёт тестам строки выгрузок из памяти и помнит, какие пути спрашивали."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FakeTextSource:
    """Отсутствующий путь выглядит пустым источником - как и файл на диске."""

    files: dict[Path, str] = field(default_factory=dict)
    reads: list[Path] = field(default_factory=list)

    def lines(self, path: Path) -> Iterator[str]:
        self.reads.append(path)
        return iter(self.files.get(path, "").splitlines(keepends=True))
