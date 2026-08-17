"""Ноль сидов при живых соседях: играть тут нечего ни на каком качестве."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.is_dead import is_dead


def test_zero_seeders_next_to_live_neighbours_is_not_a_show() -> None:
    """«Наруто»: 124-гигабайтный пак с нулём сидов обходил сериал на 91 сид."""
    assert is_dead(rel(seeders=0), alive=91)
    assert not is_dead(rel(seeders=1), alive=91), "порог тут ровно ноль, а не доля"


def test_a_pool_where_everyone_is_at_zero_is_not_touched() -> None:
    """Понижать там некого и не в пользу кого."""
    assert not is_dead(rel(seeders=0), alive=0)
