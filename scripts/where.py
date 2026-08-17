"""Где объявлен символ: карта имён из `docs/map.md` без фасадов и заглушек.

Служебная ручка разреза: `scripts/where.py cluster pick_franchise` печатает модуль,
в котором символ ОБЪЯВЛЕН, а не тот, который его реэкспортирует.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Модули-фасады: они только реэкспортируют, объявления в них не ищем.
_FACADE = re.compile(r"^torrcast/[a-z_]+\.py$")


def homes(name: str, root: Path) -> list[str]:
    """Все файлы, где символ объявлен, слоистые впереди фасадов."""
    rows = (root / "docs" / "map.md").read_text(encoding="utf-8").splitlines()
    found = []
    for row in rows:
        cells = [cell.strip(" `") for cell in row.split("|")]
        if len(cells) > 4 and cells[1] == name:
            found.append(cells[3])
    return sorted(found, key=lambda path: (bool(_FACADE.match(path)), path))


def main(argv: list[str]) -> int:
    """Печатает по строке на символ: имя и его дом."""
    root = Path.cwd()
    for name in argv:
        places = homes(name, root)
        print(f"{name}: {' | '.join(places) if places else 'НЕ НАЙДЕН'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
