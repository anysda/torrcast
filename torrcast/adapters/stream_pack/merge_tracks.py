"""Собирает сегмент из картинки перекода и звука копии.

Зовёт её выкладка упаковщика (:mod:`torrcast.adapters.stream_pack.packer_publish`).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.stream_pack.piece_with_head import piece_with_head
from torrcast.domain.probe_settings import _TIMEOUT
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.domain.video_scale import video_scale

#: Сколько байт заголовка хватает, чтобы прочитать шкалы его дорожек.
_HEAD_PEEK: Final = 64 << 10


def _show_scale(head: Path | None) -> int:
    """Шкала картинки показа: ею и обязана быть собрана склейка; ``0`` - спросить негде.

    🔴 Умолчание муксера тут не годится. Замер: показ написан шкалой 16000 тиков в секунду,
    а склейка того же места тем же ffmpeg - 12288. Склейка уходит наружу со своим
    заголовком, приёмник берёт его как новое описание дорожек и читает им ВСЕ следующие
    куски - то есть чужая шкала уводит не одну склейку, а весь хвост показа.
    """
    if head is None:
        return 0
    try:
        with head.open("rb") as fh:
            return video_scale(fh.read(_HEAD_PEEK))
    except OSError:
        return 0


def merge_tracks(
    video: Path,
    audio: Path,
    dst: Path,
    timeout: float = _TIMEOUT,
    shift: float = 0.0,
    container: SegmentContainer = MPEGTS,
    heads: tuple[Path | None, Path | None] = (None, None),
    *,
    run: Callable[..., Any] = subprocess.run,
) -> bool:
    """Собрать сегмент из картинки ``video`` и звука ``audio``; ``False`` — не вышло.

    Ради этого и написано: **звук показа должен быть одним непрерывным
    потоком одного кодировщика**, а перекодированный кусок приносит свой.

    Кадровая сетка AAC отсчитывается от начала прогона ffmpeg: первый кадр встаёт на
    ``-ss`` этого прогона, дальше через 1024 сэмпла (21.33 мс). Упаковщик и кодировщик —
    разные прогоны с разными ``-ss``, поэтому их сетки сдвинуты друг относительно друга на
    произвольную долю кадра. Пока куски берутся из одного прогона, стык звука точен до
    микросекунды; на **первом** куске каждого захода перекода звук копии обрывается, а
    звук перекода начинается позже — замер на «Тачках 3»: дыра **40.7 мс** на
    3973.678 при нуле на всех соседних стыках. Приёмник Q70D платит за эту дыру не сорока
    миллисекундами, а 2–5 секундами: он пересобирает синхронизацию.

    Поэтому наружу идёт картинка перекода со звуком копии — того самого прогона, что
    выложил соседние куски. Границы у них одни (сетка одна), метки абсолютные (``-copyts``),
    так что склейка — это переупаковка без единого перекодирования: 0.09–0.11 с на кусок
    12 МБ, замер.

    ``shift`` (:func:`timeline_shift`) кладёт картинку перекода на ленту **этого прогона**:
    у прогона с нуля метки сдвинуты на кадр вперёд относительно времени фильма, и без
    поправки на голове захода приёмник получает кадр с меткой НАЗАД, а на хвосте — дыру
    в кадр. Стоит поправка одного ``-itsoffset``: переупаковка та же.

    ⚠️ Не вышло — врать нельзя: возвращаем ``False``, и :meth:`Packer.publish` решает,
    что выкладывать вместо склейки — копию своего прогона (если она не тяжелее потолка)
    или перекод как есть.

    ``container`` - чем режет показ, то есть каким муксером собирать склейку. Отдельным
    доводом, а не умолчанием: наружу этот файл уходит под именем куска, и муксер обязан
    быть тем же, каким собраны его соседи. Пока здесь стоял один ``mpegts``, склейка на
    fMP4 писалась чужим муксером под расширением ``.m4s``.

    ``heads`` - заголовки тех прогонов, что сделали картинку и звук
    (:func:`torrcast.adapters.stream_pack.chunk_head.chunk_head`). Нужны они ровно на CMAF и
    ровно на ВХОДЕ: голый фрагмент открыть нечем (:func:`_fed`). Приезжают доводом, а не
    ищутся тут по соседству: «заголовок лежит рядом с куском» - это не свойство файла, а
    знание выкладки о том, чей это кусок, и заголовок, взятый от чужого захода, не роняет
    склейку, а молча отдаёт мусор - код возврата ноль при 334 строках ошибок.

    На выходе склейка остаётся такой, какой её собрал муксер, - самостоятельным куском с
    ``ftyp moov`` впереди. Снимать этот заголовок здесь нельзя: голый кусок перестаёт
    читаться и нашими же приборами, а ими выкладка проверяет, с того ли места склейка
    (:func:`torrcast.adapters.stream_pack.track_starts.track_starts`). Что с ним делать
    дальше, решает выкладка (:func:`torrcast.adapters.stream_pack._own_head._own_head`):
    кусок со своим заголовком - ровно та же форма, которую она приставляет сама.

    ⚠️ Метки готовой склейки лентой показа НЕ являются, и здесь это не чинится ничем: на
    CMAF муксер начинает счёт своего прогона с нуля (замер: восемь способов попросить его об
    обратном, все восемь дали ноль). Ставит склейку на ленту показа уже готовой
    (:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`) тот, кто знает, вместо
    какого куска она уедет.

    ``run`` - чем поднимается ffmpeg. Доводом, а не именем модуля: прежде стенд подменял
    :mod:`subprocess` целиком, вместе с его же классом ошибок, - то есть знал не договор
    склейки, а список имён внутри неё.
    """
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts"]
    # Полкадра - порог осмысленности: ниже него сдвига нет, а не «есть, но крошечный».
    if abs(shift) >= 0.001:
        command += ["-itsoffset", f"{shift:.6f}"]
    command += [
        "-i", piece_with_head(video, heads[0]), "-i", piece_with_head(audio, heads[1]),
        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
    ]  # fmt: skip
    if container == FMP4:
        command += ["-movflags", "cmaf+frag_keyframe+empty_moov+default_base_moof"]
        scale = _show_scale(heads[1])
        if scale:
            command += ["-video_track_timescale", f"{scale}"]
        command += ["-f", "mp4"]
    else:  # без обоих нулей mpegts двигает ВСЕ метки на 0.7 + 0.7 = 1.4 с
        command += ["-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts"]
    command += ["-y", str(dst)]
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        dst.unlink(missing_ok=True)
        return False
    if done.returncode != 0 or not dst.exists() or dst.stat().st_size <= 0:
        dst.unlink(missing_ok=True)
        return False
    return True
