"""Где кончается готовый кусок по его собственным пакетам, а не по списку нарезки.

Спрашивает сверка прогона упаковки (:func:`torrcast.adapters.stream_pack.packer_finished._reached`)
о последнем куске фильма, когда список нарезки не дотянул до конца сетки.
"""

from __future__ import annotations

import contextlib
import math
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.domain.probe_settings import _TIMEOUT


def piece_end(
    piece: Path, timeout: float = _TIMEOUT, *, run: Callable[..., Any] = subprocess.run
) -> float:
    """Конец последнего пакета ЛЮБОЙ дорожки куска, секунды ленты; ``nan`` - не прочли.

    Список нарезки сегментного муксера пишет конец куска по опорной дорожке, то есть по
    видео, а не по самой длинной. Замер на стенде («Любовь. Смерть. Роботы» s1e1,
    WEB-DL mkv): видео в файле кончается на 1034.4 с, звук на 1038.4 с, паспорт 1038.46 с.
    Список закрывает последний кусок на 1034.508, а в самом куске звук идёт до 1038.545.
    Недобор четыре секунды звал здоровый хвост обрывом входа: три перепаковки подряд,
    кусок списан, и плеер стоял за 8.5 с до конца, пока не кончался отсчёт следующей серии.

    Оборванный вход так не выглядит: кусок закрывает муксер, и звук за видео не
    продолжается (замер :func:`torrcast.usecases.warm.segment_end.segment_end`, 5 релизов).
    """
    command = [
        "ffprobe", "-v", "error", "-show_entries", "packet=pts_time,duration_time",
        "-of", "csv=p=0", str(piece),
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return math.nan
    latest = math.nan
    for line in str(done.stdout or "").splitlines():
        parts = line.strip().rstrip(",").split(",")
        try:
            end = float(parts[0])
        except ValueError:
            continue  # ``N/A`` вместо метки: пакет без времени конца не называет
        with contextlib.suppress(IndexError, ValueError):
            end += float(parts[1])
        latest = end if math.isnan(latest) else max(latest, end)
    return latest


__all__ = ["piece_end"]
