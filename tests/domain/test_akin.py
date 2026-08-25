"""Зеркало :mod:`torrcast.domain.akin`: когда два имени считаются одним и тем же."""

from torrcast.domain.akin import _akin


def test_a_name_that_lives_inside_the_other_is_the_same_name() -> None:
    """Родство тут ненаправленное: продолжение и его основа узнают друг друга оба."""
    assert _akin("брат", "брат-2")
    assert _akin("брат-2", "брат")


def test_two_different_names_stay_two_different_names() -> None:
    assert not _akin("брат", "сестра")


def test_a_name_that_was_not_said_is_akin_to_nothing() -> None:
    """Пустая строка входит в любую: без этой отсечки родным оказался бы каждый."""
    assert not _akin("", "брат")
    assert not _akin("брат", "")
