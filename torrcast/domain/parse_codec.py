"""Правило parse codec; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_1 import _AV1_RE, _H264_RE, _HEVC_RE, _MPEG4_RE


def _parse_codec(text: str) -> str | None:
    if _HEVC_RE.search(text):
        return "HEVC"
    if _H264_RE.search(text):
        return "H.264"
    if _MPEG4_RE.search(text):
        return "MPEG-4"
    return "AV1" if _AV1_RE.search(text) else None


__all__ = ["_parse_codec"]
