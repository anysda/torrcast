"""Зеркало :mod:`torrcast.domain.paired`: два имени из одних и тех же слов."""

from torrcast.domain.paired import _paired


def test_the_same_words_in_another_order_are_the_same_name() -> None:
    """Трекеры переставляют слова названия, и картина от этого другой не становится."""
    assert _paired(["матрица", "перезагрузка"], ["перезагрузка", "матрица"])


def test_a_word_in_another_form_still_pairs() -> None:
    """Падеж - не другое слово: «матрицы» встаёт в пару к «матрица»."""
    assert _paired(["матрица", "перезагрузки"], ["перезагрузка", "матрицы"])


def test_names_of_different_length_are_not_a_pair() -> None:
    assert not _paired(["матрица", "перезагрузка"], ["матрица"])


def test_a_single_word_is_never_paired() -> None:
    """Одно слово совпадает со слишком многим, и парой это не считается."""
    assert not _paired(["матрица"], ["матрица"])


def test_a_name_with_a_word_of_its_own_is_not_a_pair() -> None:
    assert not _paired(["матрица", "перезагрузка"], ["матрица", "революция"])
