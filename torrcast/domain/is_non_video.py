"""Правило is non video; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_2 import _NON_VIDEO_RE, _VIDEO_MARKER_RE


def _is_non_video(text: str) -> bool:
    return bool(_NON_VIDEO_RE.search(text)) and (not _VIDEO_MARKER_RE.search(text))


__all__ = ["_is_non_video"]
