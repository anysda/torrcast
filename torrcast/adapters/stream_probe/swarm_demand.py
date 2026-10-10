"""Спрос на раздачу: читаем файл с места, которого нет в кэше, чтобы рой его вёз."""

from __future__ import annotations

import contextlib
import time
import urllib.request

from torrcast.adapters.torrserver.stream_reads import READS


def swarm_demand(source_url: str, offset: int, seconds: float) -> None:
    """Читать ``seconds`` секунд файл с ``offset``: служба просит у роя куски оттуда.

    Мерит не этот читатель, а счётчик приёма службы (живой замер 10-10): поток служба
    отдаёт только целыми кусками, кусок раздачи 4-16 МБ, и на живом рое в 150 КБ/с за
    4 с к читателю не пришло ни байта, пока счётчик показывал 1.16 Мбит/с. Молчание и
    обрыв - не ошибка: спрос создан, остальное скажет счётчик.
    """
    began = time.monotonic()
    request = urllib.request.Request(source_url, headers={"Range": f"bytes={offset}-"})
    with (
        contextlib.suppress(Exception),
        READS.opened(
            source_url, lambda: urllib.request.urlopen(request, timeout=seconds)
        ) as answer,
    ):
        while answer is not None and time.monotonic() - began < seconds:
            if not answer.read1(1 << 16):
                break
