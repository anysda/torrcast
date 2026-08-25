"""Зеркало :mod:`torrcast.domain.spell`: русское имя, записанное латиницей на слух."""

from torrcast.domain.spell import spell


def test_a_russian_name_becomes_latin_letters() -> None:
    """Трекеры пишут русское название латиницей, и запрос обязан его находить."""
    assert spell("Матрица") == "matritsa"


def test_the_letter_x_is_written_the_way_it_is_read() -> None:
    """«ks» вместо «x»: у одного и того же имени должен получаться один ответ."""
    assert spell("Max") == "maks"


def test_a_latin_name_is_left_as_it_is() -> None:
    assert spell("Brother") == "brother"
