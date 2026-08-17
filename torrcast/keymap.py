"""Совместимый фасад карты опорных кадров.

Разбор индексов контейнеров живёт в :mod:`torrcast.domain.frames`, чтение раздачи
диапазонными запросами - в :mod:`torrcast.adapters.frames`.
"""

from torrcast.adapters.frames.http_range_reader import HttpRangeReader as Reader
from torrcast.adapters.frames.keyframes import HEAD_PEEK, keyframes
from torrcast.domain.frames.keymap import KeyMap, Point, video_track

__all__ = ["HEAD_PEEK", "KeyMap", "Point", "Reader", "keyframes", "video_track"]
