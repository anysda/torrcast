"""Откроет ли декодер вкладки копию, зашедшую в файл с ``-ss``; спрашивает начало показа."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Any

from torrcast.domain.hls_wait import ENTRY_TIMEOUT

#: Типы NAL среза картинки AVC: 1 - обычный срез, 5 - срез IDR.
_SLICE, _IDR = 1, 5

#: Сколько пакетов входа разбирает декодер. MMCO на невиданные картинки всплывает уже на
#: втором (BD-AVC 5212 МБ с 177.837, 300 и 1000 с; x264 с ref=4); 16 - с запасом, это
#: 0.2-0.3 МБ того же чтения, что тут же понадобится упаковке.
ENTRY_PACKETS = 16

#: Метка строк декодера AVC в журнале ffmpeg: жалобы демультиплексора сюда не попадают.
_DECODER = b"[h264 @"


def opens_clean(
    source_url: str,
    seek: float,
    timeout: float = ENTRY_TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> bool | None:
    """Откроет ли декодер копию с ``-ss seek``: ``True``/``False``, ``None`` - не сверили.

    🔴 Флаг опорного кадра в контейнере - это ещё не вход. У BD-AVC с открытым GOP
    опорные кадры - I-срезы без IDR, и следующие за ними P-кадры несут команды MMCO на
    картинки, стоявшие ДО I-кадра. Декодер, начавший с такого кадра, этих картинок не
    видел: вкладка отвечает ``PIPELINE_ERROR_DECODE``, и hls.js по кругу просит те же
    куски. Живой замер на «Интерстелларе» 5212 МБ с закладки 177.837: копия - ни одного
    кадра за 99 с, сплошной перекод того же места - кадр через 0.28 с после загрузки.

    Но I без IDR сам по себе не приговор: x264 с ``open-gop`` без MMCO на входе вкладка
    (Chromium, hls.js) играет с первого куска. Поэтому IDR - сразу ``True``, а вход без IDR
    решает декодер: те же :data:`ENTRY_PACKETS` пакетов, что уже прочитаны, он разбирает
    локально, без второго похода в раздачу. Жалоба декодера (MMCO на невиданные картинки,
    нет PPS - у mkv с заголовками только в шапке) - ``False``, тишина - ``True``. Все восемь
    сэмплов замера (IDR; x264 open-gop без MMCO на входе - три; x264 с MMCO - два; без PPS;
    BD-AVC) легли одинаково во вкладке и здесь.

    Сырой поток ``-f h264`` приходит в Annex B (муксер сам ставит ``h264_mp4toannexb``),
    поэтому тип среза виден без разбора контейнера. Молчание - не приговор: не AVC, не
    прочиталось, среза нет, декодер не успел - ``None``, и показ идёт прежним путём. Обе
    ступени укладываются в один потолок ``timeout``: он слагаемое бюджета старта.
    """
    began = clock()
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{seek:.3f}",
        "-i", source_url, "-map", "0:v:0", "-c", "copy", "-frames:v", str(ENTRY_PACKETS),
        "-f", "h264", "pipe:1",
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    first = _first_slice_idr(done.stdout)
    if first is not False:
        return first
    return _decodes_quietly(done.stdout, timeout - (clock() - began), run)


def _decodes_quietly(stream: bytes, left: float, run: Callable[..., Any]) -> bool | None:
    """Молчит ли декодер на уже прочитанном потоке; ``None`` - не успел или не запустился."""
    if left <= 0:
        return None
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "h264", "-i", "pipe:0",
        "-f", "null", "-",
    ]  # fmt: skip
    try:
        done = run(command, input=stream, capture_output=True, timeout=left, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return _DECODER not in done.stderr


def _first_slice_idr(stream: bytes) -> bool | None:
    """IDR ли первый срез картинки в потоке Annex B; ``None`` - среза нет."""
    at = stream.find(b"\x00\x00\x01")
    while at >= 0 and at + 3 < len(stream):
        kind = stream[at + 3] & 0x1F
        if kind in (_SLICE, _IDR):
            return kind == _IDR
        at = stream.find(b"\x00\x00\x01", at + 3)
    return None
