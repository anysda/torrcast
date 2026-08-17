"""Секундомер критического пути старта: где именно уходят секунды до картинки.

Зачем отдельная лента, а не `print` со временем: старт живёт **в двух процессах**. CLI
ищет, греет раздачи и задаёт вопросы, а сам показ уезжает в transient-юнит, и склеить их
логи по времени иначе нечем. Поэтому метки пишутся в один файл, путь к которому едет
юниту через окружение (:data:`~torrcast.domain.timeline_env.TIMELINE_ENV`), а время
берётся стенное - монотонное у двух процессов разное.

Выключено по умолчанию: без переменной окружения метки в файл не идут и не стоят ничего.
В недельный след фаза при этом уходит всегда (:mod:`torrcast.ports.journal`): он и заведён
затем, чтобы знать про сеанс всё, и точки секундомера подбирает даром.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.ports.journal import journal


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


def read(path: str | Path) -> list[dict[str, Any]]:
    """Лента меток по возрастанию времени."""
    found: list[dict[str, Any]] = []
    with contextlib.suppress(OSError):
        for raw in Path(path).read_text("utf-8").splitlines():
            with contextlib.suppress(ValueError):
                found.append(json.loads(raw))
    return sorted(found, key=lambda entry: float(entry.get("at", 0.0)))
