"""Проверяет чтение оригинального названия из первой скобки статьи."""

from tests.articles import ATTACK_FILM, CARS
from torrcast.domain.facts.latin_title import latin_title


def test_the_bracket_with_the_language_carries_the_original_name() -> None:
    """«(англ. Cars)» - ровно то имя, которым картину подписывают индексеры."""
    assert latin_title(CARS) == "Cars"


def test_the_original_name_is_never_a_string_of_hieroglyphs() -> None:
    """У японского кино скобка двуязычна, и латиница в ней - ещё не название.

    «(яп. 進撃の巨人 エンド オブ ザ ワールド Shingeki no Kyojin: Endo obu za Wārudo)» проходило
    прежнюю проверку («латиница есть, кириллицы нет») целиком, вместе с иероглифами, и
    ровно этой строкой поиск шёл добирать раздачу. Искать по ней нечего.
    """
    assert latin_title(ATTACK_FILM) == ""


def test_a_bracket_without_latin_is_not_an_original_name() -> None:
    """Скобка «(род. 1950)» у режиссёра - тоже скобка, но имени картины в ней нет."""
    assert latin_title("«Брат» — фильм Алексея Балабанова (род. 1959) 1997 года.") == ""
