"""Разница лент копии и перекода одного места фильма.

Спрашивает её выкладка упаковщика перед склейкой (:mod:`torrcast.usecases.feed_pack`).
"""

from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.domain.probe_settings import _TIMEOUT


def timeline_shift(
    copy: Path,
    recode: Path,
    timeout: float = _TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> float | None:
    """Разница лент копии и перекода одного места, секунды; ``None`` - не сверили.

    Оба куска делают разные ffmpeg, поэтому разницу нельзя предполагать нулевой: она
    измеряется по их первым пакетам. Общий :attr:`~torrcast.adapters.stream_pack.grid.Grid.origin`
    теперь заранее поднимает метки выше нуля во всех заходах, и исправная упаковка обычно даёт здесь
    ноль. Сам замер остаётся страховкой от любого нового расхождения двух путей.

    Считается по первым пакетам обоих кусков: у обоих это один и тот же опорный кадр
    фильма, поэтому разница их меток - и есть сдвиг ленты. Дороже одного ``ffprobe`` на
    файл (первые четыре пакета) это не стоит.

    ``None`` - сверить не вышло (нет ffprobe, битый кусок) или разница вышла больше
    секунды: столько между двумя кусками ОДНОГО места быть не может, значит мерили не то.

    ``run`` - чем поднимается ffprobe. Доводом, а не именем модуля: прежде стенд подменял
    :mod:`subprocess` целиком, вместе с его же классом ошибок.
    """
    marks: list[float] = []
    for path in (copy, recode):
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", "%+#4",
            "-show_entries", "packet=pts_time", "-of", "csv=p=0", str(path),
        ]  # fmt: skip
        try:
            done = run(command, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        found = []
        for line in done.stdout.decode("utf-8", "replace").splitlines():
            with contextlib.suppress(ValueError):
                found.append(float(line.strip().rstrip(",")))
        if not found:
            return None
        marks.append(min(found))
    shift = marks[0] - marks[1]
    return None if abs(shift) > 1.0 else shift
