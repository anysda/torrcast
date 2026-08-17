"""Запасной подтвердил своё имя кадром из ffprobe; зовёт поиск честного соседа."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.domain.rank_settings import HD_HEIGHT, HONEST_RATIO
from torrcast.domain.release import Release


def honest_shot(release: Release, media: Media) -> bool:
    """Запасной подтвердил своё имя: кадр из ffprobe не ниже заявленной ступени. Имя
    молчало — тогда достаточно, чтобы внутри оказался HD.
    """
    if not media.height:
        return False
    if release.height:
        return media.frame >= release.height * HONEST_RATIO
    return media.frame >= HD_HEIGHT
