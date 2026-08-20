"""Проверяет, назвала ли статья имя картины на чужом языке - на любом письме."""

from tests.articles import CARS, NATIVE_SERIES, NOT_CINEMA, UTENA
from torrcast.domain.facts.named_original import named_original


def test_the_latin_bracket_is_a_named_original() -> None:
    """«(англ. Cars)» - имя названо, и разбирать его для этого не надо."""
    assert named_original(CARS)


def test_hieroglyphs_are_a_named_original_too() -> None:
    """🔴 TC-567. Скобка с иероглифами - это НАЗВАННОЕ имя, а не его отсутствие.

    Разбор оригинала отдаёт тут пустую строку намеренно: искать раздачу по иероглифам
    нечего (:func:`~torrcast.domain.facts.latin_title.latin_title`). Но пустота эта - про
    поиск, а не про картину, и читать её как «своего имени у картины нет» значит
    записать японское аниме в отечественное кино и отдать зрителю его японскую дорожку.
    """
    assert named_original(UTENA)


def test_an_article_without_a_language_bracket_names_nothing() -> None:
    """Отечественная картина: чужого имени первая фраза не называет вовсе."""
    assert not named_original(NATIVE_SERIES)


def test_a_bracket_without_a_language_is_not_a_name() -> None:
    """Скобка бывает не про имя: у города в ней запись произношения, а не оригинал."""
    assert not named_original(NOT_CINEMA["Новосибирск"])


def test_a_year_of_birth_is_not_a_name_either() -> None:
    """«(род. 1959)» устроена ровно как скобка имени, и языком «род» не является."""
    assert not named_original("«Брат» — фильм Алексея Балабанова (род. 1959).")


def test_the_russian_language_names_no_other_name() -> None:
    """«(рус. …)» - то же самое имя, которым картина и подписана: чужого имени нет."""
    assert not named_original("«Брат» (рус. Брат) — российский фильм 1997 года.")
