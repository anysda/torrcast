"""Зеркало :mod:`torrcast.domain.franchises`: картины, разложенные по франшизам."""

from torrcast.domain.franchises import franchises
from torrcast.domain.picture import Picture


def test_the_parts_of_one_franchise_land_under_one_key() -> None:
    found = franchises([Picture(title="Брат", year=1997), Picture(title="Брат 2", year=2000)])

    assert list(found) == ["брат"]
    assert [p.title for p in found["брат"]] == ["Брат", "Брат 2"]


def test_every_franchise_comes_out_in_the_order_of_its_parts() -> None:
    """Внутри франшизы порядок тот же, что на экране: сначала ранняя часть."""
    found = franchises([Picture(title="Брат 2", year=2000), Picture(title="Брат", year=1997)])

    assert [p.title for p in found["брат"]] == ["Брат", "Брат 2"]


def test_different_franchises_stay_under_their_own_keys() -> None:
    found = franchises([Picture(title="Брат", year=1997), Picture(title="Матрица", year=1999)])

    assert sorted(found) == ["брат", "матрица"]
