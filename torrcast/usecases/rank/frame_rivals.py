"""Знаменатель живости ступени 1080p; зовёт порядок меню."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.release import Release
from torrcast.usecases.rank.is_full_hd import is_full_hd


def frame_rivals(
    releases: list[Release], groups: Mapping[int, tuple[object, ...]]
) -> dict[tuple[object, ...], int]:
    """Сиды сильнейшего соперника ниже 1080p в каждой группе."""
    rivals: dict[tuple[object, ...], int] = {}
    for release in releases:
        key = groups[id(release)]
        if not is_full_hd(release, 0):
            rivals[key] = max(rivals.get(key, 0), release.seeders)
    return rivals
