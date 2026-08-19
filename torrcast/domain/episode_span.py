"""Правило episode span; используют модели и фасады разбора имён."""

from __future__ import annotations

from torrcast.domain._name_data.data_3 import _EPISODE_COUNT_RE, _EPISODE_SPAN_RES


def _episode_span(text: str) -> tuple[int, ...]:
    for pattern in _EPISODE_SPAN_RES:
        match = pattern.search(text)
        if match:
            start, end = (int(match.group("start")), int(match.group("end")))
            if 1 <= start <= end:
                return tuple(range(start, end + 1))
    match = _EPISODE_COUNT_RE.search(text)
    if match:
        count, total = (int(match.group("count")), int(match.group("total")))
        if 1 <= count <= total:
            return tuple(range(1, count + 1))
    return ()


__all__ = ["_episode_span"]
