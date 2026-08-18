"""Единственная дверь в недельный след: событие кладётся в очередь и всё.

Через неё ходят и схема событий рядом, и щупы, и порт журнала."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from torrcast.adapters.filesystem.trace_journal.session_id import session_id
from torrcast.adapters.filesystem.trace_journal.writer import _put


def emit(phase: str, event: str, **fields: Any) -> None:
    """Положить событие в недельный след. Не блокирует и не пишет на диск сам.

    ``phase`` - крупная фаза (``search``/``select``/``play``/``warm``/``timeline``/
    ``note``/``session``/``error``), ``event`` - конкретное событие внутри неё. Остальное -
    поля события: числа, строки, короткие списки. Всё, что не сериализуется в JSON, роняется
    вместе с записью - диагностика не имеет права ронять показ.
    """
    record: dict[str, Any] = {
        "at": round(time.time(), 3),
        "sid": session_id(),
        "pid": os.getpid(),
        "phase": phase,
        "event": event,
    }
    record.update(fields)
    try:
        json.dumps(record, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    _put(record)
