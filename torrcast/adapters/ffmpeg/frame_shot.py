"""Снимает один кадр показа через ffmpeg; зовёт картинка карточки плеера."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Final

#: Сколько ждём ffmpeg, секунды. Кадр берётся из уже выложенной сетки, то есть с
#: собственной раздачи, - дольше этого он не едет даже с холодного старта.
_SHOT_TIMEOUT: Final = 20.0
#: Качество jpeg (шкала ffmpeg: 2 лучшее, 31 худшее). Двойка весит лишнего, а
#: карточка плеера рисует картинку в пару сотен точек шириной.
_QUALITY: Final = "4"


def frame_shot(source: str) -> bytes | None:
    """Один кадр из потока показа как jpeg; не вышло - ``None``.

    Это ЗАПАСНОЙ путь, а не постер: владелец сказал прямо - «кадр это не постер он будет
    не о чем нужен скрейпинг автономный». Нужен он ровно затем, чтобы карточка не
    оставалась молча пустой, когда постера не нашлось: нет английской статьи, нет строки
    ``| image =`` в её инфобоксе, Википедия ответила 429 или сеть легла.

    Источником назван адрес раздачи HLS, а не файл на диске: сегменты бывают и
    самостоятельными (``.ts``), и осколками, которые без ``init.mp4`` не открываются
    вовсе (``.m4s``), - а по манифесту ffmpeg собирает и то, и другое сам. Ходит он при
    этом на СВОЙ же серв, в локальную сеть, наружу ни байта.
    """
    with tempfile.TemporaryDirectory(prefix="torrcast-shot-") as home:
        shot = Path(home) / "frame.jpg"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", source,
            "-frames:v", "1", "-q:v", _QUALITY, "-f", "image2", str(shot),
        ]  # fmt: skip
        try:
            done = subprocess.run(command, capture_output=True, timeout=_SHOT_TIMEOUT, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0 or not shot.exists() or shot.stat().st_size == 0:
            return None
        return shot.read_bytes()
