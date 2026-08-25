"""Зеркало :mod:`torrcast.domain.unbranded`: название без имени телеканала перед ним."""

from torrcast.domain.unbranded import _unbranded


def test_the_channel_in_front_of_the_title_is_not_part_of_the_title() -> None:
    """Один и тот же фильм трекеры подписывают каналом и без него."""
    assert _unbranded("BBC: Планета Земля") == "Планета Земля"


def test_a_title_without_a_channel_is_left_as_it_is() -> None:
    assert _unbranded("Брат") == "Брат"
