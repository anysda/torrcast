"""Зеркало :mod:`torrcast.domain._media_picture`: что паспорт говорит о картинке."""

from torrcast.domain.media import Media


def test_the_scope_frame_is_judged_by_width_not_by_height_alone() -> None:
    """Обрезанный по вертикали кадр - всё ещё 1080p, и судит это ширина."""
    media = Media(height=800, width=1920)

    assert (media.frame, media.quality) == (1080, "1080p")


def test_a_combed_frame_says_so_in_its_own_quality_line() -> None:
    """Порядок полей из потока сильнее имени раздачи: чересстрочное зовётся 1080i."""
    assert Media(height=1080, width=1920, field_order="tt").quality == "1080i"
