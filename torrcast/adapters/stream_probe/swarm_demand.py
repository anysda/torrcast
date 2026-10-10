"""Скорость роя под настоящим спросом: читаем файл с места, которого нет в кэше."""

from __future__ import annotations

import contextlib
import time
import urllib.request

from torrcast.adapters.torrserver.stream_reads import READS


def swarm_demand(source_url: str, offset: int, seconds: float) -> float:
    """Байт в секунду, которые раздача отдала за ``seconds`` чтения с ``offset``.

    Счётчик службы на вехах прогрева врёт в обе стороны: голову, уже лежащую в кэше,
    ffprobe читает без роя, и живой рой меряется нулём. Здесь спрос настоящий - место,
    которого не читал ни прогрев, ни ffprobe, - и меряется то, что пришло к нам, а не
    то, что служба насчитала. Молчание и обрыв - ноль: байт не пришло.
    """
    began = time.monotonic()
    taken = 0
    request = urllib.request.Request(source_url, headers={"Range": f"bytes={offset}-"})
    with (
        contextlib.suppress(Exception),
        READS.opened(
            source_url, lambda: urllib.request.urlopen(request, timeout=seconds)
        ) as answer,
    ):
        while answer is not None and time.monotonic() - began < seconds:
            chunk = answer.read1(1 << 16)
            if not chunk:
                break
            taken += len(chunk)
    return taken / max(time.monotonic() - began, seconds)
