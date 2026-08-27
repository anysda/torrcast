"""Честная строка про авто-выбор крупнейшего видеофайла раздачи; печатает запуск показа.

Правило, о котором строка, живёт рядом:
:func:`torrcast.usecases.playback.file_picker._default_file` («фильму - самый крупный видеофайл»).
"""

from __future__ import annotations

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.torr_file import TorrFile


def pack_note(files: list[TorrFile]) -> str:
    """Честная строка про выбор крупнейшего видеофайла; выбора не было — пусто.

    «Фильму — самый крупный видеофайл» — авто-решение, и на раздаче, где видеофайлов
    несколько, оно обязано назвать себя: зритель читает, сколько их, что играется
    крупнейший и какова его доля в видеобайтах раздачи. Строка называет факт и не судит
    его: порога тут нет, отбраковка сборника — не эта работа.

    Видеофайлы считаются той же меркой, что у самого выбора
    (:func:`torrcast.adapters.stream_probe.pick_video_file.pick_video_file`). Один видеофайл — это
    не решение, а единственный вариант, и строка про него была бы шумом: на здоровой
    раздаче она молчит.
    """
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    total = sum(f.size for f in videos)
    if len(videos) < 2 or not total:
        return ""
    return (
        f"видеофайлов в раздаче {len(videos)} - "
        f"играю крупнейший, его доля {max(f.size for f in videos) / total:.2f}"
    )
