"""Зеркало :mod:`torrcast.domain.kind`: чем картина бывает и чем не бывает."""

from typing import get_args

from torrcast.domain.kind import Kind


def test_a_picture_is_a_film_a_series_or_neither() -> None:
    """Род решает, как картину показывать; четвёртого рода в продукте нет."""
    assert get_args(Kind) == ("movie", "tv", "other")
