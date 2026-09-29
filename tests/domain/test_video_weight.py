"""Зеркало веса видеодорожки: паспорт, честная оценка по размеру или ``-1``."""

from __future__ import annotations

from torrcast.domain.media import Media
from torrcast.domain.video_weight import video_weight


def test_the_passport_weight_wins_over_the_size() -> None:
    """Паспорт назвал вес - он и идёт, не оценка."""
    media = Media(duration=1000.0, tracks=(), video="h264", video_bps=4_000_000.0)

    assert video_weight(media, 1_000_000_000) == (4.0, False)


def test_a_silent_passport_falls_back_to_the_file_size() -> None:
    """HEVC в mkv веса не несёт: вес по размеру файла, помеченный оценкой."""
    media = Media(duration=1000.0, tracks=(), video="hevc")

    assert video_weight(media, 125_000_000) == (1.0, True)


def test_no_weight_and_no_size_is_minus_one() -> None:
    """Ни паспорта, ни размера - ``-1``, а не выдуманный ноль."""
    media = Media(duration=1000.0, tracks=(), video="hevc")

    assert video_weight(media, 0) == (-1.0, False)
