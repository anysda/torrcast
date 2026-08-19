"""Считает, на сколько поднята вся лента фильма; сдвиг уезжает в каждый заход ffmpeg."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Callable
from typing import Any

from torrcast.adapters.pack_memory import _ORIGIN, _ORIGIN_LOCK
from torrcast.domain.hls_settings import AUDIO_PRIMING
from torrcast.domain.hls_wait import PILOT_TIMEOUT
from torrcast.ports.journal.slot import journal


def _reorder_slack(
    source_url: str,
    timeout: float = PILOT_TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> float | None:
    """На сколько метки начала фильма уходят ниже нуля, секунды; ``None`` - не прочли.

    Спрашивается ОДИН ffprobe и сразу тремя способами, потому что ни один из трёх не
    работает на всех контейнерах:

    * ``pts - dts`` первых пакетов - прямой ответ там, где dts в файле есть (mp4: замер на
      ролике - pts 0.000 при dts -0.080);
    * ``-dts`` тех же пакетов - на случай, когда лента начинается ниже нуля сама по себе,
      а не из-за перестановки;
    * ``has_b_frames / кадров в секунду`` - **единственный** ответ для mkv, где dts не
      хранится вовсе. Замер на живой раздаче: у первых двух пакетов ``dts_time`` = ``N/A``,
      и первые два способа молчат, а ffmpeg тем временем достраивает те же dts сам и
      уводит начало ниже нуля ровно на эту величину.

    Берётся наибольшее из трёх: переоценка стоит миллисекунд, недооценка возвращает дефект
    (:func:`pack_origin`). Читается голова файла и только она (``-read_intervals``) - то,
    что к этому времени уже прогрето (:func:`pull_head`).

    ``run`` - чем поднимается ffprobe. Параметром, а не именем модуля: прежде стенд
    подменял ``run`` в самом :mod:`subprocess`, то есть глушил запуск процессов всему
    прогону разом, а мерил при этом разбор трёх ответов.
    """
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-read_intervals", "%+#4",
        "-show_entries", "stream=has_b_frames,avg_frame_rate:packet=pts_time,dts_time",
        "-of", "json", source_url,
    ]  # fmt: skip
    try:
        found = run(command, capture_output=True, text=True, timeout=timeout, check=True)
        payload = json.loads(found.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    slack: list[float] = []
    for number, packet in enumerate(payload.get("packets") or []):
        if not isinstance(packet, dict):
            continue
        pts, dts = _seconds(packet.get("pts_time")), _seconds(packet.get("dts_time"))
        if dts is None:
            continue
        slack.append(-dts)
        # ⚠️ ``pts - dts`` считается ТОЛЬКО у первого пакета: ниже нуля лента уходит ровно
        # на его перестановку. У пакетов в середине эта разница - глубина перестановки
        # вообще (замер на живой раздаче: 0.167 с у третьего пакета против 0.083 у начала,
        # а по фильму она доходит до 0.417), и брать её значило бы сдвигать ленту фильма
        # на полсекунды там, где хватает двух кадров.
        if number == 0 and pts is not None:
            slack.append(pts - dts)
    for stream in payload.get("streams") or []:
        if not isinstance(stream, dict):
            continue
        rate = _seconds(stream.get("avg_frame_rate", "0/0"))
        depth = stream.get("has_b_frames")
        if rate and rate > 0 and isinstance(depth, int) and depth > 0:
            slack.append(depth / rate)
    return max((0.0, *slack)) if slack else None


def _seconds(raw: Any) -> float | None:
    """Число из поля ffprobe: секунды или дробь ``24/1``; ``None`` - поля нет или ``N/A``."""
    if not isinstance(raw, str):
        return None
    head, _, tail = raw.partition("/")
    try:
        return float(head) / float(tail) if tail else float(head)
    except (ValueError, ZeroDivisionError):
        return None


def pack_origin(
    source_url: str,
    timeout: float = PILOT_TIMEOUT,
    *,
    slack_of: Callable[[str, float], float | None] = _reorder_slack,
) -> float:
    """На сколько вперёд сдвигается вся лента этого фильма, секунды. Считается раз на файл.

    🔴 Ровно тут рождался обратный ход меток на ПЕРВОМ стыке - тот, на котором приёмник
    бросал разбор (``Parsed buffers not in DTS sequence`` → ``pipeline_error 16``) и показ
    умирал молча, два запуска из пяти.

    Механизм (замерено, а не выведено). Начало фильма лежит НИЖЕ нуля: у релиза с
    B-кадрами первый пакет видео идёт с ``dts = pts - задержка перестановки`` (замер на
    ролике: pts 0.000, dts -0.083), а наш звук вдобавок начинается на набивку кодировщика
    раньше (:data:`AUDIO_PRIMING`). Отрицательных меток mpegts не выражает, и муксер
    двигает их сам - но двигает **каждый файл отдельно**, потому что сегментный муксер
    открывает под каждый кусок свой mpegts. Первому куску сдвиг нужен, соседнему уже нет:
    v0 уезжает на ленте «время фильма + сдвиг», v1 - на честном времени фильма, и на их
    стыке метки идут НАЗАД. Дальше все стыки чистые, поэтому дефект и жил только на первом.
    Замер на ролике: v0 DTS 0.000..7.958 против v1 DTS 7.917.., откат -0.042 с; куски при
    этом честные, ни одного общего кадра у них нет - назад идут только метки.

    ``-avoid_negative_ts disabled`` от этого не спасает и никогда не спасал: он снимает
    сдвиг с ВНЕШНЕГО, сегментного муксера, а внутренние mpegts его не наследуют вовсе
    (сегментный копирует им ``max_delay``, но не ``avoid_negative_ts``) - и сдвиг просто
    переезжает внутрь, из «одного на прогон» становясь «своим у каждого куска».

    Лечится это единственным способом: **лента фильма одна на все заходы**. Сдвиг
    называется явно (``-output_ts_offset``), считается один раз на файл и уезжает в каждый
    заход - живой упаковки, прогрева, перекода. Тогда ни одному муксеру двигать нечего
    (метки уже выше нуля), первый кусок ничем не отличается от прочих, а заход из середины
    после ``-ss`` встаёт с тем же началом ленты, что и заход от нуля. Проверено обоими
    концами: заход с нуля и заход после ``-ss`` дают на одном и том же куске
    **побайтово те же метки**.

    Считается сдвиг с запасом и намеренно: переоценка стоит нескольких лишних миллисекунд
    начала на всей ленте разом (ни один потребитель абсолютных меток такой разницы не
    видит), недооценка возвращает дефект целиком. Слагаемых два - задержка перестановки
    видео и набивка нашего звука, - и берётся не большее из них, а сумма: какое из двух
    окажется ниже нуля первым, решает порядок чередования потоков, а не мы.

    Не прочли (файл не открылся, ffprobe не дожил) - остаётся набивка звука: гадать про
    видео нечем, а мёртвый вход всё равно не упакуется.

    ``slack_of`` - чем меряется провал ленты ниже нуля. Параметром, а не именем внутри
    модуля: замер поднимает ffprobe на живом файле, а здесь считается округление и
    память на файл, и стенду нужно назвать ответ замера, не заводя раздачи.
    """
    with _ORIGIN_LOCK:
        ready = _ORIGIN.get(source_url)
    if ready is not None:
        return ready
    delay = slack_of(source_url, timeout)
    # Вверх до миллисекунды: в команду сдвиг уезжает с тремя знаками, и округление вниз
    # оставило бы метки на доли миллисекунды ниже нуля - то есть вернуло бы муксеру повод
    # сдвинуть первый кусок самому.
    origin = math.ceil(((delay or 0.0) + AUDIO_PRIMING) * 1000.0) / 1000.0
    with _ORIGIN_LOCK:
        origin = _ORIGIN.setdefault(source_url, origin)
    journal().mark("начало ленты", сдвиг=origin, померено=delay is not None)
    return origin
