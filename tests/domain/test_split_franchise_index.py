"""Зеркало :mod:`torrcast.domain.split_franchise_index`: номер части, отделённый от имени."""

from torrcast.domain.split_franchise_index import split_franchise_index


def test_a_number_at_the_end_of_the_query_is_the_number_of_the_part() -> None:
    assert split_franchise_index("Матрица 2") == ("Матрица", 2)


def test_a_query_without_a_number_is_all_name() -> None:
    assert split_franchise_index("  Матрица  ") == ("Матрица", None)


def test_a_number_the_query_itself_introduced_is_left_inside_the_name() -> None:
    """«Эпизод 4» человек назвал сам: искать «Звёздные войны» и брать четвёртую - не то."""
    assert split_franchise_index("Звёздные войны: Эпизод 4") == ("Звёздные войны: Эпизод 4", None)
