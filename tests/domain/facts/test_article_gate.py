"""Проверяет гейты статьи: про кино ли она и того ли типа, что спросили."""

from tests.articles import BREAKING_BAD, HP_FRANCHISE, NOT_CINEMA
from torrcast.domain.facts.article_gate import _about_cinema, _fits_type


def test_a_franchise_article_passes_the_cinema_gate_but_a_biography_still_does_not() -> None:
    """Поблажка «серия фильмов» ровно одна и косвенный падеж вообще не открывает.

    Слово «фильмов» ловится только в связке со словом «серия»: у Эммы Уотсон в статье
    стоит «в фильмах о Гарри Поттере», и её паспорт справке по-прежнему не достаётся.
    """
    assert _about_cinema("Гарри Поттер (серия фильмов)", HP_FRANCHISE)
    assert not _about_cinema(
        "Уотсон, Эмма",
        "Эмма Шарлотта Дюэрре Уотсон (англ. Emma Charlotte Duerre Watson) — "
        "британская актриса, известная по ролям в фильмах о Гарри Поттере.",
    )


def test_neither_a_person_nor_a_book_is_about_cinema() -> None:
    """Главное ограждение: человек, город, компания и книга гейт не проходят."""
    for heading, extract in NOT_CINEMA.items():
        assert not _about_cinema(heading, extract), heading


def test_a_type_the_article_never_names_does_not_silence_it() -> None:
    """Гейт типа отказывает на противоречии, а не на молчании.

    «Во все тяжкие» открывается словами «американская телевизионная криминальная драма»:
    слова «сериал» там нет. Требуй гейт явного слова - справка замолчала бы на картинах,
    которые сегодня знает. Зато обратный вопрос («это фильм?») статья опровергает сама.
    """
    assert _fits_type(True, "Во все тяжкие", BREAKING_BAD)
    assert not _fits_type(False, "Во все тяжкие", BREAKING_BAD)
    assert _fits_type(None, "Во все тяжкие", BREAKING_BAD), "тип неизвестен - сверять нечем"
