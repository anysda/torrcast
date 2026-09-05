"""Читает настоящее место, откуда показ реально пошёл; зовёт запасной путь ожидания картинки.

Файла нет - значит спрашивать нечего: заход не разошёлся с закладкой, либо показ ещё не
добежал до :func:`torrcast.adapters.stream_pack.mark_landed.mark_landed`. Тогда закладка,
данная доводом, - то же число, каким CLI сверялся до TC-1002, а не худшее враньё.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from torrcast.adapters.stream_pack.landed_path import landed_path


def read_landed(out: Path, default: float) -> float:
    """Настоящее место старта, а без файла или при битой записи - ``default``."""
    with contextlib.suppress(OSError, ValueError):
        return float(landed_path(out).read_text(encoding="utf-8"))
    return default
