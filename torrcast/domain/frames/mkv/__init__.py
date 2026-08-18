"""Карта опорных кадров mkv: индекс ``Cues``.

Общее для всех контейнеров — в :mod:`torrcast.domain.frames.keymap`, вход - в
:func:`torrcast.adapters.frames.keyframes.keyframes`. Здесь только матрёшка EBML.

В mkv есть собственный индекс перемотки — элемент ``Cues``. В нём для каждого опорного
кадра лежат время и позиция кластера в байтах, то есть готовая карта GOP: длительность —
разница времён, вес — разница позиций. Лежит он в хвосте файла, а его адрес — в
``SeekHead`` в голове. Замер: «Моана 2» (3.4 ГБ, 1119 опорных кадров) — 0.45 МБ и
4.3 с холодным роем, «Моана» 2016 (4.5 ГБ, 2830 опорных) — 2.1 с.
"""

from __future__ import annotations

from torrcast.domain.frames.mkv.head import Head as Head
from torrcast.domain.frames.mkv.ids import CLUSTER as CLUSTER
from torrcast.domain.frames.mkv.ids import CUE_CLUSTER_POSITION as CUE_CLUSTER_POSITION
from torrcast.domain.frames.mkv.ids import CUE_POINT as CUE_POINT
from torrcast.domain.frames.mkv.ids import CUE_TIME as CUE_TIME
from torrcast.domain.frames.mkv.ids import CUE_TRACK as CUE_TRACK
from torrcast.domain.frames.mkv.ids import CUE_TRACK_POSITIONS as CUE_TRACK_POSITIONS
from torrcast.domain.frames.mkv.ids import CUES as CUES
from torrcast.domain.frames.mkv.ids import CUES_CHUNK as CUES_CHUNK
from torrcast.domain.frames.mkv.ids import DURATION as DURATION
from torrcast.domain.frames.mkv.ids import HEAD_BYTES as HEAD_BYTES
from torrcast.domain.frames.mkv.ids import INFO as INFO
from torrcast.domain.frames.mkv.ids import SEEK as SEEK
from torrcast.domain.frames.mkv.ids import SEEK_HEAD as SEEK_HEAD
from torrcast.domain.frames.mkv.ids import SEEK_ID as SEEK_ID
from torrcast.domain.frames.mkv.ids import SEEK_POSITION as SEEK_POSITION
from torrcast.domain.frames.mkv.ids import SEGMENT as SEGMENT
from torrcast.domain.frames.mkv.ids import TIMESTAMP_SCALE as TIMESTAMP_SCALE
from torrcast.domain.frames.mkv.keys import keys as keys
from torrcast.domain.frames.mkv.uint import uint as uint
from torrcast.domain.frames.mkv.vint import vint as vint
from torrcast.domain.frames.mkv.walk import walk as walk

__all__ = [
    "CLUSTER",
    "CUES",
    "CUES_CHUNK",
    "CUE_CLUSTER_POSITION",
    "CUE_POINT",
    "CUE_TIME",
    "CUE_TRACK",
    "CUE_TRACK_POSITIONS",
    "DURATION",
    "HEAD_BYTES",
    "INFO",
    "SEEK",
    "SEEK_HEAD",
    "SEEK_ID",
    "SEEK_POSITION",
    "SEGMENT",
    "TIMESTAMP_SCALE",
    "Head",
    "keys",
    "uint",
    "vint",
    "walk",
]
