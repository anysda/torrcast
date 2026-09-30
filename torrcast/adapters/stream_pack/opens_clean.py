"""Откроет ли декодер приёмника копию, зашедшую в файл с ``-ss``; спрашивает начало показа."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Any

from torrcast.domain.hls_wait import PILOT_TIMEOUT

#: Типы NAL среза картинки AVC: 1 - обычный срез, 5 - срез IDR.
_SLICE, _IDR = 1, 5


def opens_clean(
    source_url: str,
    seek: float,
    timeout: float = PILOT_TIMEOUT,
    *,
    run: Callable[..., Any] = subprocess.run,
) -> bool | None:
    """Первый кадр копии с ``-ss seek`` - IDR; ``False`` - не IDR, ``None`` - не сверили.

    🔴 Флаг опорного кадра в контейнере - это ещё не вход. У BD-AVC с открытым GOP
    опорные кадры - I-срезы без IDR, и следующие за ними P-кадры несут команды MMCO на
    картинки, стоявшие ДО I-кадра. Декодер, начавший с такого кадра, этих картинок не
    видел: ffmpeg с ``-err_detect explode`` падает на первом же куске («mmco: unref short
    failure»), а вкладка - ``PIPELINE_ERROR_DECODE``, и hls.js по кругу просит те же
    куски. Живой замер на «Интерстелларе» 5212 МБ с закладки 177.837: копия со входа
    174.758 - ни одного кадра за 99 с, сплошной перекод того же места - кадр через 0.28 с
    после загрузки. С нуля тот же файл играет: там единственный IDR, и дальше декодер
    идёт без разрыва.

    Стоит один ffmpeg на один кадр, и байты те же, что тут же читает заход упаковки.
    Сырой поток ``-f h264`` приходит в Annex B (муксер сам ставит ``h264_mp4toannexb``),
    поэтому тип среза виден без разбора контейнера. Молчание - не приговор: не AVC, не
    прочиталось, среза нет - ``None``, и показ идёт прежним путём.
    """
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{seek:.3f}",
        "-i", source_url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
        "-f", "h264", "pipe:1",
    ]  # fmt: skip
    try:
        done = run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return _first_slice_idr(done.stdout)


def _first_slice_idr(stream: bytes) -> bool | None:
    """IDR ли первый срез картинки в потоке Annex B; ``None`` - среза нет."""
    at = stream.find(b"\x00\x00\x01")
    while at >= 0 and at + 3 < len(stream):
        kind = stream[at + 3] & 0x1F
        if kind in (_SLICE, _IDR):
            return kind == _IDR
        at = stream.find(b"\x00\x00\x01", at + 3)
    return None
