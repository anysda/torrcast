"""Чтение ленты за все сутки каталога в порядке времени.

Читает её разбор ``cast log`` (:func:`torrcast.domain.digest.digest`) и щупы."""

from __future__ import annotations

import contextlib
import json
from typing import Any

from torrcast.adapters.filesystem.trace_journal.log_dir import log_dir
from torrcast.adapters.filesystem.trace_journal.log_path import _PREFIX, _SUFFIX


def records(since: float = 0.0) -> list[dict[str, Any]]:
    """Лента за все сутки в каталоге, по возрастанию времени, не раньше ``since``."""
    found: list[dict[str, Any]] = []
    with contextlib.suppress(OSError):
        for path in sorted(log_dir().glob(f"{_PREFIX}*{_SUFFIX}")):
            with contextlib.suppress(OSError):
                for raw in path.read_text("utf-8").splitlines():
                    # Нечитаемая строка значит «этой строки нет» и ничего больше. Разбор и
                    # проверка стоят под одним suppress намеренно: врозь неразобранная
                    # строка оставляла в `rec` ПРЕДЫДУЩУЮ запись, и та уходила в выдачу
                    # вторым разом, а битая первая строка роняла `cast log` целиком. Хвост
                    # ленты рвётся законно: писатель - демон, и последняя запись может
                    # оборваться на середине вместе с погашенным показом.
                    with contextlib.suppress(TypeError, ValueError):
                        rec = json.loads(raw)
                        if isinstance(rec, dict) and float(rec.get("at", 0.0)) >= since:
                            found.append(rec)
    return sorted(found, key=lambda e: float(e.get("at", 0.0)))
