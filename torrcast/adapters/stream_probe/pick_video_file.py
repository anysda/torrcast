"""Самый крупный видеофайл раздачи, он же фильм; образ диска - отказ навсегда.

Зовут его отбор релиза и старт показа."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.not_found_error import NotFoundError

if TYPE_CHECKING:
    TorrFile = Any


def pick_video_file(files: list[TorrFile]) -> TorrFile:
    """Самый крупный видеофайл раздачи, он же фильм; образ диска — :class:`NotFoundError`.

    Тип отказа здесь - не украшение, а решение отбора (:func:`torrcast.cli._silenced`):
    :class:`InfraError` - это «рой промолчал, про раздачу не узнали ничего», и такую
    раздачу промолчавшая очередь спрашивает ещё раз. А тут метаданные приехали целиком
    и ответ известен навсегда: видеофайла в раздаче нет. Второй спрос дал бы ровно тот
    же ответ за те же секунды - как у «нужной серии в раздаче нет»
    (:meth:`torrcast.cli._Series.choose`), и тип у них один.
    """
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    if not videos:
        raise NotFoundError(
            "в раздаче нет отдельного видеофайла (похоже на образ диска) - "
            "возьми другой релиз: cast <запрос> --release N"
        )
    return max(videos, key=lambda f: f.size)
