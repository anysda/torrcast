"""Зеркало :mod:`torrcast.domain.group_weight`: чем меряется живость группы картин."""

from torrcast.domain.group_weight import _group_weight
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(copies: int) -> Picture:
    return Picture(
        title="Брат",
        year=1997,
        releases=[Release(raw_name="Брат", title="Брат") for _ in range(copies)],
    )


def test_the_weight_is_the_count_of_releases_across_the_whole_group() -> None:
    """Вес - это раздачи всех картин группы, а не число самих картин."""
    assert _group_weight({"брат": [_picture(2), _picture(3)]}, "брат") == 5


def test_a_group_nobody_seeds_weighs_nothing() -> None:
    assert _group_weight({"брат": [_picture(0)]}, "брат") == 0
