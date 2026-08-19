"""Карта опорных кадров файла целиком; её отдают разборы, а читает сетка сегментов."""

from __future__ import annotations

from typing import NamedTuple

from torrcast.domain.frames.keymap.point import Point


class KeyMap(NamedTuple):
    """Карта опорных кадров файла и цена её снятия."""

    duration: float
    points: tuple[Point, ...]
    taken: int
    requests: int
    #: Контейнер, ``mkv`` или ``mp4``. Он уже известен по первым байтам головы, и знать
    #: его дальше по пути стоит ноль запросов, а решает многое: сколько головы греть,
    #: чтобы ffmpeg открыл вход, - у mp4 там ``moov`` на мегабайты, у mkv хватает
    #: килобайт.
    kind: str = ""
    #: Номер дорожки видео, названный самим файлом (элемент ``Tracks`` у mkv); ``None`` -
    #: файл дорожку не назвал, и выбирать её придётся эвристикой
    #: (:func:`~torrcast.domain.frames.keymap.video_track.video_track`).
    video: int | None = None
