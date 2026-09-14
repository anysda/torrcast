"""Проверяет разбор ответа Википедии: кандидат → статья → описание и Q-идентификатор."""

from typing import Any

from tests.articles import (
    CARS,
    LINER,
    MOANA,
    REVOLUTIONS,
    ROBOCOP_FILM,
    ROBOCOP_SERIES,
    robocop_reply,
    wiki_reply,
)
from torrcast.domain.facts.read_pages import _read_pages
from torrcast.domain.facts.titles_for import titles_for


def test_a_disambiguation_page_is_not_a_description() -> None:
    """«Моана» голым именем — статья про полинезийское слово, а не про кино."""
    about, entities, _ = _read_pages(wiki_reply(), {("Моана", 2016): titles_for("Моана", 2016)})
    assert about[("Моана", 2016)] == MOANA
    assert entities[("Моана", 2016)] == "Q1183953"


def test_an_unconfirmed_picture_gets_nothing_rather_than_someones_else_film() -> None:
    """Ремейк 2026 года в тексте себя не называет — и справки у него не будет."""
    about, entities, _ = _read_pages(wiki_reply(), {("Моана", 2026): titles_for("Моана", 2026)})
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
    about, entities, _ = _read_pages(payload, {("тачки", 2006): ["тачки"]})
    assert about[("тачки", 2006)] == CARS
    assert entities[("тачки", 2006)] == "Q182153"


def test_a_series_does_not_describe_the_film_it_was_made_from() -> None:
    """Сериал 1994 года называет год фильма своим текстом - тип и разводит эти картины."""
    key = ("Робокоп", 1987)
    names = titles_for(*key)
    assert names.index("Робокоп (телесериал)") < names.index("Робокоп (фильм, 1987)")
    about, entities, _ = _read_pages(robocop_reply(), {key: names}, frozenset(), {key: "movie"})
    assert about[key] == ROBOCOP_FILM
    assert entities[key] == "Q172975"


def test_without_a_hinted_type_the_series_takes_the_films_place() -> None:
    """Отрицательная проба: не подскажи тип - и зритель прочитает про чужую картину."""
    key = ("Робокоп", 1987)
    about, _, _ = _read_pages(robocop_reply(), {key: titles_for(*key)})
    assert about[key] == ROBOCOP_SERIES


def _liner_reply() -> dict[str, Any]:
    """Ответ Википедии на имя «Титаник»: статья о пароходе, а не о фильме."""
    return {
        "query": {
            "pages": [
                {
                    "title": "Титаник",
                    "extract": LINER,
                    "pageprops": {"wikibase_item": "Q25173"},
                }
            ]
        }
    }


def test_an_exact_name_from_the_offline_map_does_not_hand_over_a_ship() -> None:
    """Карта IMDb освобождает от сверки года, но не делает пароход фильмом.

    🔴 TC-957. Статья «Титаник» - про британский пароход: года фильма в ней нет, и одна
    лишь точность имени пускала её зрителю как справку о картине 1997 года.
    """
    key = ("Титаник", 1997)

    about, entities, _ = _read_pages(_liner_reply(), {key: ["Титаник"]}, {key}, {key: "movie"})

    assert about == {}
    assert entities == {}


def test_an_exact_name_still_restores_a_picture_that_never_names_its_year() -> None:
    """Послабление живо: статья назвалась произведением своего жанра - года с неё не спросят."""
    key = ("Матрица: Революция", 2003)
    reply: dict[str, Any] = {
        "query": {
            "pages": [
                {
                    "title": key[0],
                    "extract": REVOLUTIONS,
                    "pageprops": {"wikibase_item": "Q207536"},
                }
            ]
        }
    }

    about, _, _ = _read_pages(reply, {key: [key[0]]}, {key}, {key: "movie"})

    assert about[key] == REVOLUTIONS


def test_an_exact_name_does_not_turn_a_character_into_its_film() -> None:
    """The title and a later mention of the film do not identify the character as the work."""
    key = ("Базз Лайтер", 2022)
    character = (
        "Базз Ла́йтер (также известен как Базз Све́тик) — вымышленный персонаж франшизы "
        "Disney и Pixar «История игрушек». Базз — экшен-фигурка внутривселенской франшизы."
    )
    reply: dict[str, Any] = {
        "query": {"pages": [{"title": key[0], "extract": character, "pageprops": {}}]}
    }

    about, _, _ = _read_pages(reply, {key: [key[0]]}, {key}, {key: "movie"})

    assert about == {}


def test_a_qualified_lightyear_cartoon_beats_its_character_page() -> None:
    """The 2022 picture has a Russian article even though its bare title is a character."""
    key = ("Базз Лайтер", 2022)
    cartoon = (
        "«Базз Лайтер» — американский компьютерно-анимационный научно-фантастический фильм, "
        "созданный киностудиями Pixar и Walt Disney Pictures."
    )
    reply: dict[str, Any] = {
        "query": {
            "pages": [
                {
                    "title": key[0],
                    "extract": "Базз Лайтер — вымышленный персонаж.",
                    "pageprops": {},
                },
                {
                    "title": "Базз Лайтер (мультфильм)",
                    "extract": cartoon,
                    "pageprops": {"wikibase_item": "Q100000"},
                },
            ]
        }
    }

    about, entities, _ = _read_pages(
        reply, {key: [key[0], "Базз Лайтер (мультфильм)"]}, {key}, {key: "movie"}
    )

    assert about == {key: cartoon}
    assert entities == {key: "Q100000"}


_LANTERNS = (
    "«Фонари́» (англ. Lanterns) — американский телесериал, основанный на комиксах "
    "издательства DC Comics о двух Зелёных Фонарях — Хэле Джордане и Джоне Стюарте."
)


def _lanterns() -> dict[str, Any]:
    return {
        "query": {
            "pages": [
                {
                    "title": "Фонари",
                    "extract": _LANTERNS,
                    "pageprops": {"wikibase_item": "Q110556821"},
                }
            ]
        }
    }


def test_a_searched_russian_heading_of_a_latin_series_is_its_article() -> None:
    """Lanterns 2026 has «Фонари»: IMDb knows that heading in 2026, the article names Lanterns."""
    key = ("Lanterns", 2026)

    about, entities, _ = _read_pages(
        _lanterns(), {key: ["Фонари"]}, set(), {key: "tv"}, {("Фонари", 2026)}
    )

    assert about == {key: _LANTERNS}
    assert entities == {key: "Q110556821"}


def test_a_russian_heading_needs_both_its_map_year_and_the_named_original() -> None:
    """Without the IMDb year, or for another Latin title, the yearless article proves nothing."""
    key, other = ("Lanterns", 2026), ("Lamps", 2026)

    assert _read_pages(_lanterns(), {key: ["Фонари"]}, {key}, {key: "tv"})[0] == {}
    assert (
        _read_pages(_lanterns(), {key: ["Фонари"]}, set(), {key: "tv"}, {("Фонари", 2025)})[0] == {}
    )
    assert (
        _read_pages(_lanterns(), {other: ["Фонари"]}, set(), {other: "tv"}, {("Фонари", 2026)})[0]
        == {}
    )


def test_a_russian_heading_naming_no_original_is_the_picture_the_map_named() -> None:
    """«Защищая твою жизнь» names neither Defending Your Life nor 1991; the IMDb map does both."""
    key = ("Defending Your Life", 1991)
    life = "«Защищая твою жизнь» - американская романтическая комедия Альберта Брукса."
    reply: dict[str, Any] = {"query": {"pages": [{"title": "Защищая твою жизнь", "extract": life}]}}
    muses: dict[str, Any] = {"query": {"pages": [{"title": "Музы", "extract": "Музы - богини."}]}}

    names: dict[tuple[str, int | None], list[str]] = {key: ["Защищая твою жизнь"]}
    assert _read_pages(reply, names, set(), {key: "movie"}, {("Защищая твою жизнь", 1991)})[0] == {
        key: life
    }
    assert _read_pages(reply, names, set(), {key: "movie"})[0] == {}
    assert _read_pages(muses, {key: ["Музы"]}, set(), {key: "movie"}, {("Музы", 1991)})[0] == {}


def test_a_russian_heading_naming_no_original_does_not_pass_a_russian_tile_or_another_year() -> (
    None
):
    """A Soviet namesake names no original too: a Russian tile or its own year keeps it out."""
    soviet = "«Опасное место» - советский фильм 1990 года."
    reply: dict[str, Any] = {
        "query": {"pages": [{"title": "Опасное место (фильм)", "extract": soviet}]}
    }
    russian: tuple[str, int | None] = ("Опасное место", 2026)
    latin: tuple[str, int | None] = ("Dangerous Place", 2026)
    for key in (russian, latin):
        names: dict[tuple[str, int | None], list[str]] = {key: ["Опасное место (фильм)"]}
        assert _read_pages(reply, names, set(), {key: "movie"}, {("Опасное место", 2026)})[0] == {}
