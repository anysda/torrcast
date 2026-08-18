"""Что лежит в каталоге кусками сетки: имена и пути глобом ``v*.ts``.

Спрашивают их упаковщик (выкладка, уборка) и лента (запас, вес, окно показа).
"""

from __future__ import annotations

from pathlib import Path


def _names(out: Path) -> list[str]:
    return [path.name for path in out.glob("v*.ts")]


def _paths(out: Path) -> list[Path]:
    return list(out.glob("v*.ts"))
