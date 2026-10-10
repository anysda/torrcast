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

#: Сколько пакетов всех дорожек читать от последнего опорного кадра. Без предела ffprobe
#: тянул файл до конца: у «Отчаянных домохозяек» s3 за последним кадром ещё 112 с звука,
#: это 65 МБ из холодного роя против бюджета в 8 с, и хвост не узнавался ни разу. Тысяча
#: двести пакетов - это последняя группа кадров и 15-30 с звука за ней.
PACKETS: Final = 1200

#: На сколько секунд звук должен уйти за последний кадр, чтобы окно назвало конец картинки
#: и без конца файла: дорожки сплетены по времени с разбегом меньше секунды.
LEAD: Final = 3.0

#: Пакеты дальше этого позади окна - не хвост: обложка-картинка стоит на нуле.
BEHIND: Final = 120.0


def picture_end(
    url: str,
    timeout: float,
    alive: Callable[[], bool] | None,
    run: Callable[[list[str], float, Callable[[], bool] | None], str],
) -> float:
    """Конец последнего видеокадра файла в секундах.

    ``inf`` - окно кончилось, а картинка всё идёт: она не короче звука, резать нечего.
    ``nan`` - не узнали (рой, отказ, пустой ответ): такой паспорт на полку не ложится.
    Перемотка встаёт по индексу файла (Cues у mkv, moov у mp4), поэтому читается лишь
    последняя группа кадров и :data:`PACKETS` пакетов за ней, а не весь звук до конца.
    """
    command = [
        "ffprobe", "-v", "error", "-read_intervals", f"{PAST_END}+#{PACKETS}",
        "-show_entries", "packet=codec_type,pts_time,duration_time", "-of", "csv=p=0", url,
    ]  # fmt: skip
    try:
        out = run(command, timeout, alive)
    except (OSError, subprocess.SubprocessError, SwarmError):
        return math.nan
    packets = [packet for line in out.splitlines() if (packet := _packet(line)) is not None]
    if not packets:
        return math.nan
    top = max(start for _kind, start, _stop in packets)
    video = [stop for kind, start, stop in packets if kind == "video" and start > top - BEHIND]
    if not video:
        return math.nan
    end = max(video)
    sound = max((start for kind, start, _stop in packets if kind == "audio"), default=-math.inf)
    if len(out.splitlines()) < PACKETS or sound - end > LEAD:
        return end  # дочитали файл или звук уже ушёл за последний кадр
    return math.inf


def _packet(line: str) -> tuple[str, float, float] | None:
    """Дорожка, начало и конец пакета из строки ffprobe; ``None`` - пакет без метки."""
    parts = [*line.strip().rstrip(",").split(","), "", "", ""]
    try:
        start = float(parts[1])
    except ValueError:
        return None  # ``N/A``: пакет без метки конца не называет
    stop = start
    with contextlib.suppress(ValueError):
        stop += float(parts[2])
    return parts[0], start, stop


__all__ = ["BEHIND", "LEAD", "PACKETS", "PAST_END", "picture_end"]
