"""Зеркало :mod:`torrcast.domain.kindred`: сходит ли картина за родню уже набранным."""

from torrcast.domain.kindred import _kindred
from torrcast.domain.picture import Picture


def test_the_same_kind_is_kinship_enough() -> None:
    """Два фильма одного имени - одна картина, сколько бы лет между ними ни было."""
    base = [Picture(title="Брат", year=1997, kind="movie")]

    assert _kindred(Picture(title="Brother", year=2019, kind="movie"), base)


def test_a_neighbouring_year_makes_kin_of_different_kinds() -> None:
    """Сериал по фильму того же года - та же картина: год тут и есть подтверждение."""
    base = [Picture(title="Брат", year=1997, kind="movie")]

    assert _kindred(Picture(title="Brother", year=1998, kind="tv"), base)


def test_another_kind_from_another_time_is_a_stranger() -> None:
    base = [Picture(title="Брат", year=1997, kind="movie")]

    assert not _kindred(Picture(title="Brother", year=2019, kind="tv"), base)


def test_nothing_to_compare_with_is_not_kinship() -> None:
    assert not _kindred(Picture(title="Брат", year=1997), [])
