"""Стоит ли смотреть на запасной релиз: зовёт поиск честного соседа на стенде."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.domain.rank_settings import HD_HEIGHT
from torrcast.domain.release import Release


def promises_more(release: Release, media: Media) -> bool:
    """Стоит ли вообще смотреть на этот запасной: обещает HD и больше, чем дал верх."""
    return release.height >= HD_HEIGHT and release.height > media.frame
