"""Зеркало :mod:`torrcast.domain.facts.dated`: статья вместе с тем, чем сверить её год."""

from torrcast.domain.facts.dated import Dated


def test_an_article_that_said_nothing_keeps_a_way_to_ask() -> None:
    """Пустые годы - это «сказать нечем», и спрашивают тогда Wikidata по её сущности."""
    row = Dated("Parasite", "Q61448040", frozenset())
    assert row.years == frozenset(), "статья про свой год промолчала"
    assert row.entity == "Q61448040", "но спросить о ней есть кого"
    assert row.kinds == frozenset(), "род тоже бывает несказанным"


def test_the_row_travels_as_a_key_and_two_equal_rows_are_one() -> None:
    """Строки складываются в множества при отсеве повторов запасной дорожки."""
    row = Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}))
    assert row == Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}))
    assert len({row, row}) == 1
