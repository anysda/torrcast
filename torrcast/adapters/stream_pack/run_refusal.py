"""Строка ffmpeg, отменяющая удачу прогона; пусто - таких строк нет."""

from __future__ import annotations

from typing import Final

#: Слова, после которых прогон не удался, каким бы кодом он ни вышел.
#:
#: 🔴 Код возврата тут не судья, и это замер, а не осторожность. ffmpeg умеет напечатать
#: ошибку демультиплексирования и выйти НУЛЁМ, причём на одном и том же месте обрыва исход
#: не повторяется: один проход даёт 0, другой 183. Отдельно от этого стоит отказ
#: мультиплексора: mpegts не принимает поток без меток (``first pts and dts value must be
#: set``) - так лежит видео в .avi, где меток нет вовсе, а при B-кадрах пуст и ``pts``
#: первого пакета. Замер на стенде (.avi, h264 с B-кадрами, 29 границ сетки): пробный
#: прогон не дал первого пакета ни разу, и без разбора этих строк единственным следом
#: события был ответ, равный самой запрошенной границе.
_MARKS: Final = (
    "error during demuxing",
    "input/output error",
    "error muxing a packet",
    "error submitting a packet",
    "must be set",
)


def run_refusal(stderr: str) -> str:
    """Первая строка отказа в выводе ffmpeg; пусто - прогон ни на что не жаловался."""
    for line in stderr.splitlines():
        folded = line.casefold()
        if any(mark in folded for mark in _MARKS):
            return line.strip()
    return ""
