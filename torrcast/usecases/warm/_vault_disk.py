"""Чем прогрев меряет диск: вес прогретого, давность показа и свободное место раздела.

Зовёт их каталог прогретого (:class:`torrcast.usecases.warm.vault.Vault`), и только он.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from torrcast.usecases.warm.settings import META


def _disk_free(root: Path) -> int:
    """Сколько байт свободно на разделе, где лежит корень прогретого; беда - ноль."""
    try:
        stat = os.statvfs(root)
    except OSError:
        return 0
    return stat.f_bavail * stat.f_frsize


def _dirs(root: Path) -> list[Path]:
    try:
        return [path for path in root.iterdir() if path.is_dir()]
    except OSError:
        return []


def _touched(path: Path) -> float:
    try:
        return (path / META).stat().st_mtime
    except OSError:
        return 0.0


def _title(path: Path) -> str:
    """Название вытесняемого показа из его паспорта; нет паспорта - пустая строка."""
    with contextlib.suppress(OSError, ValueError):
        found = json.loads((path / META).read_text(encoding="utf-8"))
        if isinstance(found, dict):
            return str(found.get("title", ""))
    return ""


def _size(path: Path) -> int:
    """Вес файла; не прочли - ноль. Ноль тут безопасен: кусок, пропавший между глобом и
    ``stat``, отдача уже переживает (404 → приёмник просит снова)."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _weigh(where: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        for path in where.rglob("v*.ts"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total
