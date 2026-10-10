"""Паспорт с длительностью по концу картинки, а не контейнера.

Зовёт его щуп паспорта (:func:`torrcast.adapters.stream_probe.probe.probe`), и только он."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Final

from torrcast.domain.media import Media

#: Насколько картинка может кончиться раньше контейнера, не меняя сетку показа. Обычный
#: релиз несёт звук за последним кадром на 0.57-1.05 с (замер на стенде, 5 релизов), и
#: этот хвост едет в последнем куске (:func:`torrcast.adapters.stream_pack.tail_end.tail_end`).
#: Дальше кусков по картинке уже нет вовсе: «Отчаянные домохозяйки» s3, WEB-DL 720p -
#: видео до 2588.5 с, русский звук и контейнер до 2702.7 с, и приёмник стоял на 2579.5.
PICTURE_GAP: Final = 2.0


def to_picture(media: Media, end: float) -> Media:
    """Паспорт, в котором длительность - конец картинки, если контейнер тянется дальше
    неё больше чем на :data:`PICTURE_GAP`.

    Из длительности паспорта считаются сетка показа, список кусков с ``ENDLIST`` и
    прогрев следующей серии. Куски режутся по видео: за последним кадром кусков нет, и
    сетка до конца контейнера обещала приёмнику то, чего упаковка не сделает никогда.
    """
    if math.isnan(end) or end <= 0 or media.duration - end <= PICTURE_GAP:
        return media
    return replace(media, duration=end)


__all__ = ["PICTURE_GAP", "to_picture"]
