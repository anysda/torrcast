"""Меряет пробным прогоном, где ffmpeg встал после ``-ss``, и переводит ответ в ленту фильма.

Запасной и для .ts единственный путь :func:`pack_start`.
"""

from __future__ import annotations

import math
import subprocess
import tempfile
import threading

from torrcast.domain.hls_wait import PILOT_TIMEOUT
from torrcast.ports.journal import journal

#: С какой метки начинается ВИДЕО этого файла, секунды. Одно число на файл
#: (:func:`_film_start`): им пробный прогон переводит свой ответ из лент контейнера в
#: ленту фильма - ту, в которой стоят :attr:`Grid.bounds`.
_FILM_START: dict[str, float] = {}
_FILM_LOCK = threading.Lock()


def _film_start(source_url: str, timeout: float = PILOT_TIMEOUT) -> float:
    """С какой метки начинается ВИДЕО этого файла. Не прочли — ``0.0``. Раз на файл.

    Это переводчик между двумя лентами, которые до TC-629 молча считались одной. Метки в
    файле лежат от ``start_time`` контейнера, а сетка (:class:`Grid`) отсчитана от начала
    фильма: ``bounds[0]`` всегда 0. У mkv и mp4 видео начинается с нуля, и разницы между
    лентами нет вовсе - поэтому дефекта и не было видно годами. У .ts и .m2ts начало любое.

    Спрашивается ровно **видео**, а не контейнер целиком: ``start_time`` формата - это
    минимум по всем потокам, а наш звук начинается на набивку кодировщика раньше видео
    (замер: формат -0.006 при видео 0.000). Взяв формат, мы сдвинули бы каждый заход на
    обычном mkv на эти миллисекунды и развели бы пробный прогон с картой опорных кадров,
    которая снята по видео.

    Одно число на файл: ffprobe тут стоит десятые доли секунды на локальном файле и до
    нескольких секунд на живой раздаче, а заходов на фильм много. Не прочли - ноль,
    и тогда работает прежнее поведение: для mkv и mp4 оно и есть верное.
    """
    with _FILM_LOCK:
        ready = _FILM_START.get(source_url)
    if ready is not None:
        return ready
    begins = 0.0
    try:
        answer = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=start_time", "-of", "csv=p=0", source_url],
            capture_output=True, text=True, timeout=timeout, check=True,
        )  # fmt: skip
        head = answer.stdout.strip().splitlines()
        value = float(head[0].split(",")[0])
        # nan/inf в ленту переводить нечем, а «N/A» ffprobe печатает словом и сюда не дойдёт.
        begins = value if math.isfinite(value) else 0.0
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        begins = 0.0
    with _FILM_LOCK:
        begins = _FILM_START.setdefault(source_url, begins)
    if begins:
        journal().mark("лента фильма", файл=source_url, начало=round(begins, 3))
    return begins


def _pilot_start(source_url: str, at: float, timeout: float = PILOT_TIMEOUT) -> float:
    """Пробный прогон в один кадр: где ffmpeg встал на самом деле. Не вышло — ``at``.

    🔴 TC-629. Ответ ПЕРЕВОДИТСЯ в ленту фильма, а не зажимается. Различать надо две
    совершенно разные вещи, которые обе выглядят как «встали позже, чем просили»:

    * **метка из чужой ленты** - сотни секунд разницы. ``-ss`` отсчитывается от начала
      контейнера, а ``-copyts`` печатает метку как она лежит в файле, то есть вместе со
      сдвигом всего контейнера. Замер на стенде: контейнер, чьё видео начинается с 600.006,
      на ``-ss 40.000`` отвечает **640.006**. Дальше это ехало в
      :func:`ffmpeg_pack_command` как ``at``, где резы считаются ``grid.start(k) - at``:
      список уходил в МИНУС целиком, сегментный муксер не резал ничего и клал **один кусок
      21.2 МБ** вместо одиннадцати по 2.1 МБ (на живом релизе 240 МБ при норме 12 МБ);
    * **штатный уезд вперёд** - единицы секунд, и это ПРАВДА о потоке, а не ошибка.
      У mpegts перемотка садится на СЛЕДУЮЩИЙ опорный кадр, а не на предыдущий, и докатки
      у него не бывает вовсе (:data:`SEEK_SHIFT`, замер репы: +1 на 89 границах; свой
      замер: ``-ss 41.000`` на .ts даёт 42.000, тогда как mkv на том же месте даёт 40.000).

    Зажать ответ границей значило бы стереть второе вместе с первым - и ровно там, где
    зажимать всего опаснее: карты опорных кадров для .ts и .m2ts взять неоткуда
    (:data:`SEEK_SHIFT` такого контейнера не знает намеренно), поэтому пробный прогон там
    не запасной путь, а ЕДИНСТВЕННЫЙ. Подменив измеренное место предполагаемым, показ
    получил бы куски с именами мест, в которых поток не начинался, - ту же беду, от которой
    бережёт :func:`pack_start`, только с другого конца.

    Поэтому лечится это переводом ленты (:func:`_film_start`), и перевод стоит одного
    ``ffprobe`` на файл: у mkv и mp4 видео начинается с нуля, сдвиг нулевой и ответ не
    меняется ни на миллисекунду, у .ts - вычитается целиком.

    ⚠️ Вычитать ``start_time`` ВСЕГО контейнера (``-start_at_zero``) нельзя: он считается по
    самому раннему потоку, а сетка стоит на опорных кадрах ВИДЕО. На обычном mkv звук
    начинается на набивку кодировщика раньше видео (замер: формат -0.006 при видео 0.000),
    и флаг сдвигал бы каждый заход на эти 6 мс - расхождение с картой на ровном месте.
    """
    with tempfile.TemporaryDirectory(prefix="torrcast-pilot-") as tmp:
        probe_path = f"{tmp}/first.ts"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts", "-ss", f"{at:.3f}",
            "-i", source_url, "-map", "0:v:0", "-c", "copy", "-frames:v", "1",
            "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", probe_path,
        ]  # fmt: skip
        try:
            subprocess.run(command, capture_output=True, timeout=timeout, check=True)
            found = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                 "packet=pts_time", "-of", "csv=p=0", "-read_intervals", "%+#1", probe_path],
                capture_output=True, text=True, timeout=timeout, check=True,
            )  # fmt: skip
        except (OSError, subprocess.SubprocessError):
            return at  # не вышло - считаем, что встали ровно на границе, и скажем об этом
        head = found.stdout.strip().splitlines()
        try:
            stood = float(head[0].split(",")[0])
        except (IndexError, ValueError):
            return at
        # 🔴 TC-629. Ответ лежит в ленте контейнера, а нужен в ленте фильма - той, в которой
        # стоят границы сетки. Уезд вперёд на опорный кадр при этом остаётся как есть: он
        # не ошибка замера, а поведение демуксера (:data:`SEEK_SHIFT`).
        return stood - _film_start(source_url, timeout)
