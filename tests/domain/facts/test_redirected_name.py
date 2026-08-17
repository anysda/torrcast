"""Проверяет узкий путь: русское имя, перенаправленное на латинский заголовок."""

from typing import Any

from tests.articles import STEINS_GATE, page
from torrcast.domain.facts.redirected_name import redirected_name


def test_a_redirect_to_a_latin_heading_gives_the_original_name_without_a_year() -> None:
    """Русское имя аниме, подписанного латиницей: перенаправление и есть ответ.

    «врата штейна» - живое перенаправление Википедии на статью ``Steins;Gate``, но статья
    эта о визуальной новелле, с которой всё началось, и киношного гейта она не проходит.
    Справка молчала, добор шёл транслитом ``vrata shteyna`` в никуда.

    Год такой статьи брать нельзя вовсе: у ``Steins;Gate`` во врезке стоит «20 августа 2026
    года выйдет ремейк новеллы», а аниме вышло в 2011-м.
    """
    names = ["врата штейна"]
    hops = {"врата штейна": "Врата штейна", "Врата штейна": "Steins;Gate"}
    pages: dict[str, Any] = {"Steins;Gate": page("Steins;Gate", STEINS_GATE, english="Steins;Gate")}

    found = redirected_name(names, hops, pages, "врата штейна")
    assert found.title == "Steins;Gate"
    assert found.year is None
    # Без перенаправления пути нет: заголовок мы назвали сами, и доказывать им нечего.
    assert not redirected_name(["Steins;Gate"], {}, pages, "Steins;Gate"), (
        "спросили латиницей - это не перенаправление русского имени"
    )


def test_a_redirect_to_a_person_is_not_an_original_name() -> None:
    """Граница узкого пути: заголовок обязан быть латиницей, а статья - произведением."""
    pages: dict[str, Any] = {
        "Дитрих Марлен": page(
            "Дитрих Марлен",
            "Мари Магдалена Дитрих (нем. Marie Magdalene Dietrich) — немецкая актриса.",
        ),
        "Nokia": page("Nokia", "Nokia Corporation — финская транснациональная компания."),
    }
    assert not redirected_name(
        ["марлен дитрих"], {"марлен дитрих": "Дитрих Марлен"}, pages, "марлен дитрих"
    )
    assert not redirected_name(["нокиа"], {"нокиа": "Nokia"}, pages, "нокиа")
