"""На сколько звук готового куска идёт дальше его картинки, по собственным пакетам куска.

Спрашивает :func:`torrcast.adapters.stream_pack.tail_end.tail_end` о последнем куске фильма,
когда список нарезки не дотянул до конца сетки.
"""

from __future__ import annotations

import contextlib
import math
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from torrcast.domain.probe_settings import _TIMEOUT


def piece_overhang(
    piece: Path,
    header: Path | None = None,
    timeout: float = _TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> float:
    """Сколько секунд любая дорожка куска идёт за его последним видеокадром; ``nan`` - не прочли.

    Список нарезки сегментного муксера пишет конец куска по опорной дорожке, то есть по
    видео, а не по самой длинной. Замер на стенде («Любовь. Смерть. Роботы» s1e1,
    WEB-DL mkv): видео в файле кончается на 1034.4 с, звук на 1038.4 с, паспорт 1038.46 с.
    Недобор по списку звал здоровый хвост обрывом входа: перепаковка по кругу, кусок
    списан, и плеер стоял до конца отсчёта следующей серии.

    Меряется РАЗНИЦА, а не конец: кусок fMP4 считает время от начала своего прогона, а не
    ленты (замер «Теория большого взрыва» s2e5: список 1203.419, в куске видео до 14.681,
    звук до 15.573), и только разница переносится на конец из списка без сдвигов.

    ``header`` - заголовок прогона для fMP4: голый кусок ``.m4s`` без него не читается
    («trun track id unknown, no tfhd was found»), и прежняя мера молча отдавала ``nan``
    на каждом показе Android TV. Кусок TS читается сам.

    Оборванный вход так не выглядит: кусок закрывает муксер, и звук за видео не
    продолжается (замер :func:`torrcast.usecases.warm.segment_end.segment_end`, 5 релизов).
    """
    source = f"concat:{header}|{piece}" if header is not None else str(piece)
    command = [
        "ffprobe", "-v", "error", "-show_entries", "packet=codec_type,pts_time,duration_time",
        "-of", "csv=p=0", source,
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return math.nan
    latest: dict[str, float] = {}
    for line in str(done.stdout or "").splitlines():
        parts = line.strip().rstrip(",").split(",")
        try:
            end = float(parts[1])
        except (IndexError, ValueError):
            continue  # ``N/A`` вместо метки: пакет без времени конца не называет
        with contextlib.suppress(IndexError, ValueError):
            end += float(parts[2])
        latest[parts[0]] = max(latest.get(parts[0], end), end)
    picture = latest.pop("video", math.nan)
    if math.isnan(picture):
        return math.nan  # не за что зацепить: конец в списке стоит именно по картинке
    return max([0.0, *(end - picture for end in latest.values())])


__all__ = ["piece_overhang"]
