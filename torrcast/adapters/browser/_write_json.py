"""Пишет JSON во временный файл рядом и переименовывает поверх цели.

Мост (:mod:`web.box`, :mod:`web.position`) и показ читают эти файлы асинхронно друг
другу, и половина объекта хуже старого - тем же основанием, что и у
:func:`torrcast.adapters.filesystem.state.write_atomic._write_atomic`. Свой вариант тут
не от нелюбви к чужому: тот - приватный помощник другого пакета (ведущее подчёркивание),
и звать его через границу пакетов значило бы опереться на чужую невидимую деталь.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Записать ``payload`` атомарно; неудача не роняет показ - только само сообщение."""
    with contextlib.suppress(OSError):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False))
            tmp.replace(path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
