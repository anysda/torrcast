"""Зеркало :mod:`torrcast.domain.unswap_layout`: запрос, набранный не в той раскладке."""

from torrcast.domain.unswap_layout import unswap_layout


def test_a_russian_word_typed_on_the_latin_layout_is_read_back() -> None:
    """Отказ на таком запросе - это отказ там, где картина есть."""
    assert unswap_layout(",hfn") == "брат"


def test_a_name_already_in_russian_letters_comes_back_the_same() -> None:
    """Перевод раскладки безвредный: русское имя через него проходит собой."""
    assert unswap_layout("Брат 2") == "брат 2"
