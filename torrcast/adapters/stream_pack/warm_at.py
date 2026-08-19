"""Тянет через рой кусок файла и выбрасывает: нужен прогретый кэш раздачи."""

from __future__ import annotations

import time
import urllib.request
from typing import Any

from torrcast.domain.warm_open import HEAD_WARM, WARM_TIMEOUT
from torrcast.ports.journal.slot import journal


def warm_at(source_url: str, offset: int, upto: int = HEAD_WARM, alive: Any = None) -> int:
    """Протянуть через рой кусок файла с ``offset`` и выбросить: нужен прогретый кэш.

    Показ читает файл ровно двумя местами: начало (заголовок контейнера, а с ним и
    ``moov`` у mp4) и то место, откуда пойдёт картинка. Пока этих байт нет в кэше
    TorrServer, ffmpeg ждёт рой, а показ ждёт ffmpeg. Под меню они берутся за время,
    пока человек отвечает.
    Лишнего трафика тут нет — ровно эти байты показ прочитает следующим действием.

    ``alive`` — жив ли ещё смысл греть: релиз, от которого показ отказался, дотягивать
    нельзя, он отъедает полосу у выбранного (:meth:`torrcast.cli.Bench.keep_only`).
    """
    began = time.monotonic()
    taken = 0
    where = f"bytes={offset}-{offset + upto - 1}"
    request = urllib.request.Request(source_url, headers={"Range": where})
    with urllib.request.urlopen(request, timeout=WARM_TIMEOUT) as answer:
        while chunk := answer.read(1 << 20):
            taken += len(chunk)
            if alive is not None and not alive():
                break
    journal().mark("прогрето", смещение=offset, байт=taken, за=round(time.monotonic() - began, 2))
    return taken
