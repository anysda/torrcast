"""Пакет записей ложится на диск: признание в потерях, дозапись, ротация.

Зовёт его только фоновый поток писателя (:meth:`_Writer._flush`)."""

from __future__ import annotations

import contextlib
import json
import os
import time
from typing import TYPE_CHECKING, Any

from torrcast.adapters.filesystem.trace_journal.log_path import log_path
from torrcast.adapters.filesystem.trace_journal.prune import _prune
from torrcast.adapters.filesystem.trace_journal.session_id import session_id

if TYPE_CHECKING:
    from pathlib import Path


def _flush(batch: list[tuple[Path, dict[str, Any]]], lost: int, marked: str) -> str:
    """Записать пакет, признаться в ``lost`` потерях и прокрутить ротацию его каталогов.

    ``marked`` - метка ротации писателя, она же и возвращается (:func:`_prune`).
    """
    if lost:
        # Переполнение очереди - единственный способ потерять решение уже ПОСЛЕ того,
        # как о нём сказали человеку. Признаваться в этом обязана сама лента: иначе
        # разбор недели уверенно прочитает пропуск как «события не было». Своего файла
        # у признания нет - потерянные записи в очередь не попали, - поэтому оно
        # ложится к первой записи пакета, то есть к соседям по потерянному месту.
        confession = {
            "at": round(time.time(), 3),
            "sid": session_id(),
            "pid": os.getpid(),
            "phase": "trace",
            "event": "lost",
            "count": lost,
        }
        batch = [(batch[0][0] if batch else log_path(), confession), *batch]
    # Обычно файл у всего пакета один и запись выходит одна, как раньше. Разные файлы
    # в одном пакете - это смена каталога ленты на ходу: тогда каждая запись едет
    # туда, куда собиралась, а не туда, где писателя застала эта смена.
    pending: dict[Path, list[dict[str, Any]]] = {}
    for path, record in batch:
        pending.setdefault(path, []).append(record)
    for path, records_ in pending.items():
        blob = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records_)
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            # O_APPEND и одна запись на файл: две ноги (команда и юнит) пишут в тот же
            # файл, атомарная дозапись держит строки целыми - как в секундомере старта.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, blob.encode("utf-8"))
            finally:
                os.close(fd)
    for directory in dict.fromkeys(path.parent for path in pending):
        marked = _prune(marked, directory)
    return marked
