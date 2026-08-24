"""Что лежит в каталоге кусками сетки: имена и пути глобом ``v*.ts``.

Спрашивают их упаковщик (выкладка, уборка) и лента (запас, вес, окно показа).
"""

from __future__ import annotations

from pathlib import Path


def _names(out: Path) -> list[str]:
    return [path.name for suffix in ("ts", "m4s") for path in out.glob(f"v*.{suffix}")]


def _paths(out: Path) -> list[Path]:
    return [path for suffix in ("ts", "m4s") for path in out.glob(f"v*.{suffix}")]
