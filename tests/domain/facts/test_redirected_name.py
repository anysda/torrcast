"""Проверяет узкий путь: русское имя, перенаправленное на латинский заголовок.

Снимок ``tests/fixtures/wiki_hatnotes.json`` снят с API русской Википедии 05-09-2026
(``prop=extracts``, ``explaintext=1``, ``exintro=1``) со статей Angel Beats!, Black
Butler, Code Geass, Steins;Gate и Run Rabbit Run. Текст Википедии доступен на условиях
CC BY-SA, список авторов - в истории каждой статьи. Сеть в тесты и в гейт не входит:
снимок обновляется руками через
``scripts/hatnoteprobe.py tests/fixtures/wiki_hatnotes.json --live``.
"""

import json
from pathlib import Path
from typing import Any

from tests.articles import STEINS_GATE, page
from torrcast.domain.facts.redirected_name import redirected_name
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows


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


def test_a_live_song_does_not_borrow_the_hatnotes_film_identity() -> None:
    """The API snapshot has a real Cyrillic redirect and a handwritten film pointer."""
    snapshot = Path(__file__).parents[2] / "fixtures" / "wiki_hatnotes.json"
    corpus = json_rows(json.loads(snapshot.read_text()))
    assert any(json_map(value)["title"] == "Run Rabbit Run" for value in corpus)
    for value in corpus:
        article = json_map(value)
        heading = str(article["title"])
        alias = str(json_map(json_rows(article["redirects"])[0])["title"])
        found = redirected_name([alias], {alias: heading}, {heading: article}, alias)
        assert found.title == ("" if heading == "Run Rabbit Run" else heading)
        assert found.year is None
