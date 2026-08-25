"""Зеркало :mod:`torrcast.domain.franchise_key`: ключ, общий у всех частей франшизы."""

from torrcast.domain.franchise_key import franchise_key


def test_every_part_of_a_franchise_answers_with_one_key() -> None:
    """Ключ на то и ключ: по нему части сходятся в одну картину, а не рассыпаются."""
    assert franchise_key("Матрица: Перезагрузка") == franchise_key("Матрица: Революция")


def test_a_title_that_is_a_franchise_by_itself_keeps_its_own_name() -> None:
    assert franchise_key("Брат") == "брат"


def test_two_different_franchises_do_not_share_a_key() -> None:
    assert franchise_key("Матрица") != franchise_key("Брат")
