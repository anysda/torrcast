"""Знаменатель живости ступени звука; зовёт порядок меню."""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.release import Release


def sound_rivals(
    releases: list[Release], groups: Mapping[int, tuple[object, ...]]
) -> dict[tuple[object, ...], int]:
    """Сиды сильнейшего соперника без обещанной русской дорожки в каждой группе."""
    rivals: dict[tuple[object, ...], int] = {}
    for release in releases:
        key = groups[id(release)]
        if not release.dubbed:
            rivals[key] = max(rivals.get(key, 0), release.seeders)
    return rivals
