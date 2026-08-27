"""Проверяет разбор ответа Википедии: кандидат → статья → описание и Q-идентификатор."""

from typing import Any

from tests.articles import CARS, MOANA, ROBOCOP_FILM, ROBOCOP_SERIES, robocop_reply, wiki_reply
from torrcast.domain.facts.read_pages import _read_pages
from torrcast.domain.facts.titles_for import titles_for


def test_a_disambiguation_page_is_not_a_description() -> None:
    """«Моана» голым именем — статья про полинезийское слово, а не про кино."""
    about, entities = _read_pages(wiki_reply(), {("Моана", 2016): titles_for("Моана", 2016)})
    assert about[("Моана", 2016)] == MOANA
    assert entities[("Моана", 2016)] == "Q1183953"


def test_an_unconfirmed_picture_gets_nothing_rather_than_someones_else_film() -> None:
    """Ремейк 2026 года в тексте себя не называет — и справки у него не будет."""
    about, entities = _read_pages(wiki_reply(), {("Моана", 2026): titles_for("Моана", 2026)})
    assert about == {}
    assert entities == {}


def test_redirects_lead_back_to_the_requested_name() -> None:
    """API нормализует имя и ведёт по перенаправлению — обратный путь читаем из ответа."""
    payload: dict[str, Any] = {
        "query": {
            "normalized": [{"from": "тачки", "to": "Тачки"}],
            "redirects": [{"from": "Тачки", "to": "Тачки (мультфильм)"}],
            "pages": [
                {
                    "title": "Тачки (мультфильм)",
                    "extract": CARS,
                    "pageprops": {"wikibase_item": "Q182153"},
                }
            ],
        }
    }
    about, entities = _read_pages(payload, {("тачки", 2006): ["тачки"]})
    assert about[("тачки", 2006)] == CARS
    assert entities[("тачки", 2006)] == "Q182153"


def test_a_series_does_not_describe_the_film_it_was_made_from() -> None:
    """Сериал 1994 года называет год фильма своим текстом - тип и разводит эти картины."""
    key = ("Робокоп", 1987)
    names = titles_for(*key)
    assert names.index("Робокоп (телесериал)") < names.index("Робокоп (фильм, 1987)")
    about, entities = _read_pages(robocop_reply(), {key: names}, frozenset(), {key: "movie"})
    assert about[key] == ROBOCOP_FILM
    assert entities[key] == "Q172975"


def test_without_a_hinted_type_the_series_takes_the_films_place() -> None:
    """Отрицательная проба: не подскажи тип - и зритель прочитает про чужую картину."""
    key = ("Робокоп", 1987)
    about, _ = _read_pages(robocop_reply(), {key: titles_for(*key)})
    assert about[key] == ROBOCOP_SERIES
