"""Вес видеодорожки для записи показа: паспортный или честно названная оценка."""

from __future__ import annotations

from torrcast.domain.estimated_video_mbit import estimated_video_mbit
from torrcast.domain.media import Media


def video_weight(media: Media, size: int) -> tuple[float, bool]:
    """Вес видеодорожки для записи, Мбит/с, и оценка ли это.

    Паспортный вес точнее; если он промолчал (HEVC в mkv его обычно не несёт), размер
    файла даёт честно названную верхнюю оценку. Нет и размера - ``-1``: старые записи
    без четвёртого столбца так и живут.
    """
    measured = media.video_bps / 1e6
    estimated = estimated_video_mbit(size, media.duration)
    return measured or estimated or -1.0, not measured and bool(estimated)
