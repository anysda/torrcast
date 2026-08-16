"""Проверки паспорта медиафайла."""

from torrcast.domain.media import Media


def test_scope_frame_and_quality() -> None:
    media = Media(height=800, width=1920)
    assert (media.frame, media.quality) == (1080, "1080p")
