"""Зеркало завода профиля тяжести: показ держит готовую ручку, а не класс адаптера."""

from __future__ import annotations

from tests.usecases.playback.world import film_keys, grid
from torrcast.recode import Weights
from torrcast.usecases.playback.heavy_profiles import HeavyProfileOf


def test_the_bound_handle_answers_the_named_contract() -> None:
    """Корень кладёт показу именно ``Weights.of``, и зовётся она ровно тремя доводами."""
    named: HeavyProfileOf = Weights.of

    made = named(film_keys(), grid(), delivered=8.0)

    assert made is not None and made.container > 0.0


def test_the_handle_answers_none_where_there_is_nothing_to_count() -> None:
    """Нечем считать - ``None``, и показ по нему решает играть как есть."""
    named: HeavyProfileOf = Weights.of

    assert named(film_keys()._replace(offset=[]), grid()) is None
