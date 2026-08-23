"""Знаменатель живости ступени звука."""

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.sound_rivals import sound_rivals


def test_a_dubbed_release_is_not_a_rival_of_another_dubbed_release() -> None:
    """Русская раздача не раздувает цену русского звука для своей соседки."""
    small = rel(name="малый дубляж", seeders=10)
    crowd = rel(name="толпа с дубляжом", seeders=200)
    foreign = rel(name="Anime [JAP+Sub]", seeders=55)
    group = (0,)

    assert sound_rivals(
        [small, crowd, foreign], {id(r): group for r in [small, crowd, foreign]}
    ) == {group: 55}


def test_a_group_without_a_foreign_rival_has_a_zero_denominator() -> None:
    dubbed = rel(name="дубляж", seeders=3)
    group = (0,)

    assert sound_rivals([dubbed], {id(dubbed): group}).get(group, 0) == 0
