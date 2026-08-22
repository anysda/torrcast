"""Зеркально проверяет оценку веса видео по целому файлу."""

from torrcast.domain.estimated_video_mbit import estimated_video_mbit


def test_file_size_gives_an_upper_video_weight_estimate() -> None:
    assert estimated_video_mbit(30_000_000_000, 6000.0) == 40.0


def test_missing_size_or_duration_gives_no_estimate() -> None:
    assert estimated_video_mbit(0, 6000.0) == 0.0
    assert estimated_video_mbit(30_000_000_000, 0.0) == 0.0
