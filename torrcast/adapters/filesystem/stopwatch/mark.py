"""Отметка фазы критического пути старта: в след - всегда, в файл - если он назван.

Зовут её все фазы старта в обоих процессах: и команда, и юнит показа."""

from __future__ import annotations

import contextlib
import json
import os
import time

from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.ports.journal.slot import journal


def mark(name: str, **facts: object) -> None:
    """Отметить фазу критического пути: в след - всегда, в файл - если он назван."""
    journal().emit("timeline", name, **facts)
    path = os.environ.get(TIMELINE_ENV)
    if not path:
        return
    line = json.dumps({"at": time.time(), "name": name, "pid": os.getpid(), **facts})
    # Дозапись строкой короче PIPE_BUF атомарна и без замка: пишут два процесса.
    with contextlib.suppress(OSError), open(path, "a", encoding="utf-8") as fp:
        fp.write(line + "\n")
