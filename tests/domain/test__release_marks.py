"""Зеркало :mod:`torrcast.domain._release_marks`: метки в зоне пометок имени."""

from torrcast.domain.release import Release


def test_a_mark_inside_the_title_itself_is_not_a_mark() -> None:
    """Метки судятся в зоне пометок: название картины из имени раздачи сначала вычёркивается."""
    release = Release(
        raw_name="Дополнительные материалы 2019 1080p", title="Дополнительные материалы"
    )

    assert release.untitled.strip() == "2019 1080p"
    assert release.extras is False


def test_a_film_with_extras_attached_stays_a_film() -> None:
    """«Фильм + допы» - это фильм: метка после плюса приложением раздачу не делает."""
    assert Release(raw_name="Кино 1080p + бонусы", title="Кино").extras is False
