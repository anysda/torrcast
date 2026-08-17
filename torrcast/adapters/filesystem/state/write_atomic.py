"""Атомарная запись JSON: временный файл рядом и переименование поверх цели.

Пишут так и настройки, и состояние: их читают на ходу, и половина файла хуже старого."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from torrcast.domain.torrcast_error import TorrcastError


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Записать JSON во временный файл рядом и переименовать поверх цели."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise TorrcastError(f"не смог записать {path}: {exc}") from exc
