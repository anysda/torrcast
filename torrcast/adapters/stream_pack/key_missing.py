"""Точно ли кусок начинается НЕ с опорного кадра. Спрашивает выкладка упаковщика."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.domain.probe_settings import _TIMEOUT


def key_missing(
    piece: Path, timeout: float = _TIMEOUT, *, run: Callable[..., Any] = subprocess.run
) -> bool:
    """Начинается ли ``piece`` НЕ с опорного кадра; ``False`` - начинается или не сверили.

    🔴 TC-698. Кусок без опорного кадра в начале - это кусок БЕЗ КАРТИНКИ, а не кусок
    похуже: наружу перекод идёт склейкой со звуком копии
    (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`), склейка копирует поток
    ``-c copy``, а копирование выбрасывает всё до первого опорного кадра. Нет его вовсе -
    выброшено ВСЁ видео, и зритель получает десять секунд звука без картинки. Живой замер:
    12 таких кусков из 39 (0.32-0.47 МБ вместо 9-11), приёмник умирает на них по три раза
    за четыре минуты, КПД показа 0.47-0.49 против 0.94 у контроля.

    Берутся такие куски у ЗАХОДА кодировщика на ВНУТРЕННИХ границах его сетки: опорный
    кадр просится на границу минус :data:`torrcast.adapters.recode.encode_settings._KEY_SLACK`,
    а на ровной сетке рез идёт по времени, а не по кадру
    (``-break_non_keyframes 1``), - и когда кадр ложится по ту сторону реза, он
    достаётся предыдущему куску, а этому не достаётся никакого. Воспроизведено вне
    показа на 23.976 к/с: заход ``v1..v3``, кусок ``v3`` начинается кадром без ``K``,
    склейка с ним даёт 354 568 байт и ноль видеопакетов.

    Молчание пробы - не приговор: ``False`` значит «сверить не вышло», и место идёт
    прежним путём. Выбрасывать готовый перекод по молчанию ffprobe нельзя, отдавать
    кусок без картинки - тем более, поэтому отвечает тут только ЗАМЕР.

    Стоит один ``ffprobe`` первого пакета - ровно столько же, сколько уже стоит сверка
    лент рядом (:func:`torrcast.adapters.stream_pack.timeline_shift.timeline_shift`).

    ``run`` - чем поднимается ffprobe. Доводом, а не именем модуля: здесь меряется
    решение выкладки, а не список имён внутри :mod:`subprocess`.
    """
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v", "-read_intervals", "%+#1",
        "-show_entries", "packet=flags", "-of", "csv=p=0", str(piece),
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    for line in done.stdout.decode("utf-8", "replace").splitlines():
        if line.strip():
            return not line.strip().startswith("K")
    return False
