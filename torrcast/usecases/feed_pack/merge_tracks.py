"""Собирает сегмент из картинки перекода и звука копии.

Зовёт её выкладка упаковщика (:mod:`torrcast.usecases.feed_pack.packer_publish`).
"""

from __future__ import annotations

from pathlib import Path

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.probe_settings import _TIMEOUT


def merge_tracks(
    video: Path, audio: Path, dst: Path, timeout: float = _TIMEOUT, shift: float = 0.0
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
    """
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts"]
    # Полкадра - порог осмысленности: ниже него сдвига нет, а не «есть, но крошечный».
    if abs(shift) >= 0.001:
        command += ["-itsoffset", f"{shift:.6f}"]
    command += [
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
        "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(dst),
    ]  # fmt: skip
    try:
        done = _state.subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except (OSError, _state.subprocess.SubprocessError):
        dst.unlink(missing_ok=True)
        return False
    if done.returncode != 0 or not dst.exists() or dst.stat().st_size <= 0:
        dst.unlink(missing_ok=True)
        return False
    return True
