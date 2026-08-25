"""Зеркало :mod:`torrcast.domain.franchise_name`: имя франшизы, снятое с названия части."""

from torrcast.domain.franchise_name import franchise_name


def test_the_words_after_the_colon_belong_to_the_part_not_to_the_franchise() -> None:
    assert franchise_name("Матрица: Перезагрузка") == "Матрица"


def test_the_number_of_the_part_is_not_part_of_the_name() -> None:
    assert franchise_name("Терминатор 2") == "Терминатор"
    assert franchise_name("Рокки IV") == "Рокки"


def test_a_name_of_one_letter_keeps_its_number() -> None:
    """Отрезать число тут нечего: от имени франшизы не осталось бы и двух букв."""
    assert franchise_name("V 2") == "V 2"


def test_a_title_of_one_word_is_its_own_franchise() -> None:
    assert franchise_name("Брат") == "Брат"
