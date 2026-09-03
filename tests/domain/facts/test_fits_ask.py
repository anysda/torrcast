"""Зеркало :mod:`torrcast.domain.facts.fits_ask`: та ли это картина или её тёзка."""

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.fits_ask import fits_ask


def test_a_namesake_of_another_year_does_not_fit() -> None:
    """🔴 Пять находок «Паразиты» разных лет вели в одну статью и делили один постер.

    Сказать человеку, что четыре из них - не они, было нечем: картинка чужой картины
    подписана НАШЕЙ строкой.
    """
    row = Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}))
    assert fits_ask(Ask("Паразиты", 2019, "movie"), row, {})
    assert not fits_ask(Ask("Паразиты", 1999, "movie"), row, {})


def test_a_year_that_the_article_kept_quiet_about_comes_from_wikidata() -> None:
    """Годы, добранные пачкой из P577, сверяются наравне с годами из категорий."""
    row = Dated("Parasite", "Q61448040", frozenset())
    assert not fits_ask(Ask("Паразиты", 2019, "movie"), row, {})
    assert fits_ask(Ask("Паразиты", 2019, "movie"), row, {"Q61448040": {2019, 2020}})


def test_a_series_does_not_take_the_poster_of_the_film_of_the_same_year() -> None:
    """«Паразиты» 2019 года - это и фильм, и сериал: без рода строки делили картинку."""
    film = Dated("Parasite", "Q61448040", frozenset({2019}), frozenset({"movie"}))
    assert not fits_ask(Ask("Паразиты", 2019, "tv"), film, {})


def test_what_the_article_kept_silent_about_is_not_a_refusal() -> None:
    """Год не спрошен или род не назван статьёй - статья годится: отказ это сказанное ДРУГОЕ.

    Строгость тут меняла бы недостающую картинку на недостающую строку, а строка нужнее.
    """
    quiet = Dated("Armitage III", "Q123", frozenset({2002}))
    assert fits_ask(Ask("Армитаж: Двойная матрица", 2002, "movie"), quiet, {})
    assert fits_ask(Ask("Матрица: Путь Нео", None, "other"), quiet, {})
