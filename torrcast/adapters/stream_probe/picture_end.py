"""Где кончается картинка файла: по последним видеопакетам его хвоста, а не по контейнеру.

Зовёт её щуп паспорта (:func:`torrcast.adapters.stream_probe.probe.probe`), и только он."""

from __future__ import annotations

import contextlib
import math
import subprocess
from collections.abc import Callable
from typing import Final

from torrcast.domain.swarm_error import SwarmError

#: Дальше конца любого фильма: перемотка сюда садится на последний опорный кадр видео,
#: и чтение до конца файла видит все кадры после него. Длительность знать заранее не
#: нужно, поэтому хвост читается одновременно с головой паспорта, а не после неё.
PAST_END: Final = "999999%"


def picture_end(
    url: str,
    timeout: float,
    alive: Callable[[], bool] | None,
    run: Callable[[list[str], float, Callable[[], bool] | None], str],
) -> float:
    """Конец последнего видеокадра файла в секундах; ``nan`` - не узнали.

    ``V`` берёт видео без обложек: у mkv с картинкой-обложкой первой дорожкой видео
    числится она. Перемотка встаёт по индексу файла (Cues у mkv, moov у mp4), поэтому
    читается лишь последняя группа кадров и звук за ней, а не весь файл.
    """
    command = [
        "ffprobe", "-v", "error", "-select_streams", "V:0", "-read_intervals", PAST_END,
        "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0", url,
    ]  # fmt: skip
    try:
        out = run(command, timeout, alive)
    except (OSError, subprocess.SubprocessError, SwarmError):
        return math.nan
    end = math.nan
    for line in out.splitlines():
        parts = [*line.strip().rstrip(",").split(","), "", ""]
        try:
            stop = float(parts[0])
        except ValueError:
            continue  # ``N/A``: пакет без метки конца не называет
        with contextlib.suppress(ValueError):
            stop += float(parts[1])
        end = stop if math.isnan(end) else max(end, stop)
    return end


__all__ = ["PAST_END", "picture_end"]
