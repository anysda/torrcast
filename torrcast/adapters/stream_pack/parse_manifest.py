"""Разбирает манифест на сегменты с длительностями; читают щупы и приёмник-заглушка."""

from __future__ import annotations

import contextlib


def parse_manifest(text: str) -> tuple[list[tuple[str, float]], bool]:
    """Манифест → пары (сегмент, длительность) и признак конца (``#EXT-X-ENDLIST``)."""
    segments: list[tuple[str, float]] = []
    seconds = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            with contextlib.suppress(ValueError):
                seconds = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            segments.append((line, seconds))
    return segments, "#EXT-X-ENDLIST" in text
