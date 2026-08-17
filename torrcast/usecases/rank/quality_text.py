"""Разрешение, которое реально поедет на ТВ; зовут строка запуска и снижение ступени."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.domain.release import Release


def quality_text(release: Release, media: Media) -> str:
    """Разрешение, которое реально поедет на ТВ. ffprobe уже прочитан — врать нечем.

    Порядок именно такой: сначала подтверждённая высота кадра, и только если ffprobe её
    не отдал (экзотика, битый заголовок) — заявка из имени. Раньше было наоборот, и
    «Моана 2» печаталась 1080p при 1150×574 внутри: заявка выигрывала у факта, то есть
    ровно та молчаливая подмена, которой быть не должно.

    Буква развёртки тоже из потока (:attr:`torrcast.stream.Media.quality`): названный
    «1080p» чересстрочник печатается «1080i» - гребёнку нельзя подписать прогрессивом.
    """
    return media.quality if media.height else (release.quality or "?")
