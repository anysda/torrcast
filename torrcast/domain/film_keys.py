"""Карта опорных кадров файла в том виде, в каком ей пользуется показ."""

from __future__ import annotations

import bisect
from typing import NamedTuple


class FilmKeys(NamedTuple):
    """Карта опорных кадров файла в том виде, в каком ей пользуется показ.

    ``at`` — времена от начала фильма, по ним строится сетка (:class:`Grid`).
    ``offset`` — где эти кадры лежат в файле; по ним греется рой под перемотку и под
    продолжение с середины (:func:`warm_at`). Списки одной длины, и порядок
    у них общий: ``at[k]`` лежит на ``offset[k]``.
    """

    duration: float
    at: list[float]
    offset: list[int]
    #: Контейнер файла, ``mkv`` или ``mp4``. Пусто - карта из кэша прошлой версии.
    kind: str = ""
    #: Время, по которому ffmpeg ИЩЕТ кадр при ``-ss``, в том же порядке, что ``at``
    #: (:data:`torrcast.domain.frames.keymap.key_map.KeyMap.via`). Пусто - совпадает с
    #: ``at``; отдельным рядом оно идёт у mp4 без списка правок (там - dts).
    via: tuple[float, ...] = ()

    def byte_at(self, seconds: float) -> int:
        """Смещение опорного кадра не позже ``seconds``; карта без смещений — ``0``.

        Не позже, а не «ближайший»: показ с этого места и начнёт читать, потому что
        ffmpeg с ``-ss`` встаёт на опорный кадр не позже запрошенного.
        """
        if not self.offset:
            return 0
        found = bisect.bisect_right(self.at, max(seconds, 0.0)) - 1
        return self.offset[min(max(found, 0), len(self.offset) - 1)]
