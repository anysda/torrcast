"""Проверяет поиск статьи, когда прямые заголовки не назвали её."""

from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_searches import wiki_searches


def test_search_keeps_the_matched_russian_heading_and_answers_the_picture() -> None:
    """English catalogue name reaches the localized article through its original title."""
    key = ("Mary and Max", 2009)
    about = "«Мэри и Макс» (англ. Mary and Max) — австралийский фильм 2009 года."

    def answer(_host: str, _path: str, params: dict[str, str]) -> Any:
        assert params["gsrsearch"] == "Mary and Max фильм"
        return {
            "query": {
                "pages": [
                    {
                        "title": "Мэри и Макс",
                        "extract": about,
                        "index": 1,
                        "pageprops": {"wikibase_item": "Q191845"},
                    }
                ]
            }
        }

    found, replies, answered = wiki_searches(FakeJsonClient(answer), [key], 1.0, {key: "movie"})

    assert found == {key: ["Мэри и Макс"]}
    assert len(replies) == 1
    assert answered == {key}


class _Names:
    def ru_names(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        names = {
            "Avatar": ["Аватар"],
            "The Muse": ["Муза"],
            "Defending Your Life": ["Защищая твою жизнь"],
        }
        return {(title, year): names[title] for title, year, _kind in pictures}

    def original_ids(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        return {}


def test_a_latin_tile_reads_its_russian_release_name_when_the_article_is_that_picture() -> None:
    """Поиск по ``Avatar фильм`` не приносит «Аватар» 2009 года; карта IMDb знает имя.

    Голое имя - статья про индуизм или про муз, «Аватар (фильм)» называет чужой оригинал,
    и их адреса в кандидаты не попадают. «Муза (фильм)» и «Защищая твою жизнь» оригинала не
    называют вовсе, и картину в них выделяет паспортная формула произведения.
    """
    avatar, muse, life = ("Avatar", 2009), ("The Muse", 1999), ("Defending Your Life", 1991)
    pages = {
        "Аватар": "Авата́р \u2014 термин индуизма, нисшествие бога.",
        "Аватар (фильм)": "«Аватар» (англ. Cyber Wars) \u2014 фильм 2009 года.",
        "Аватар (фильм, 2009)": "«Авата́р» (англ. Avatar) \u2014 американский фильм 2009 года.",
        "Муза": "Музы \u2014 богини в древнегреческой мифологии.",
        "Защищая твою жизнь": "«Защищая твою жизнь» \u2014 романтическая комедия Альберта Брукса.",
        "Муза (фильм)": "«Муза» \u2014 кинофильм 1999 года.",
    }

    def answer(_host: str, _path: str, params: dict[str, str]) -> Any:
        if "gsrsearch" in params:
            return {"query": {"pages": []}}
        asked = params["titles"].split("|")
        found = [{"title": t, "extract": e, "index": 1} for t, e in pages.items() if t in asked]
        return {"query": {"pages": found}}

    found, replies, answered = wiki_searches(
        FakeJsonClient(answer),
        [avatar, muse, life],
        1.0,
        {avatar: "movie", muse: "movie", life: "movie"},
        names=_Names(),
    )

    assert found == {
        avatar: ["Аватар (фильм, 2009)"],
        muse: ["Муза (фильм)"],
        life: ["Защищая твою жизнь"],
    }
    assert len(replies) == 6
    assert answered == {avatar, muse, life}


class _Renamed:
    def ru_names(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        return {(title, year): ["Львица", "Спецназ: Львица"] for title, year, _kind in pictures}

    def original_ids(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]:
        return {(title, year): ["tt13111078"] for title, year, _kind in pictures}


def _renamed_series(sparql: Any) -> tuple[Any, ...]:
    """IMDb files «Спецназ: Львица» under «Lioness»; the article keeps the first original."""
    key = ("Lioness", 2023)
    pages = {
        "Львица (телесериал)": ("«Львица» (англ. The Lioness) \u2014 телесериал 2023 года.", "Q1"),
        "Спецназ: Львица": (
            "«Спецназ: Львица» (англ. Special Ops: Lioness) \u2014 американский шпионский "
            "телесериал. Премьера состоялась 23 июля 2023 года на Paramount+.",
            "Q116199566",
        ),
    }

    def answer(host: str, _path: str, params: dict[str, str]) -> Any:
        if "query" in params and "SELECT" in params["query"]:
            return sparql(params["query"])
        if "gsrsearch" in params:
            return {"query": {"pages": []}}
        asked = params["titles"].split("|")
        found = [
            {"title": t, "extract": e, "index": 1, "pageprops": {"wikibase_item": q}}
            for t, (e, q) in pages.items()
            if t in asked
        ]
        return {"query": {"pages": found}}

    return key, wiki_searches(FakeJsonClient(answer), [key], 1.0, {key: "tv"}, names=_Renamed())


def _imdb(**ids: str) -> Any:
    rows = [
        {"item": {"value": f"http://www.wikidata.org/entity/{q}"}, "imdb": {"value": tt}}
        for q, tt in ids.items()
    ]
    return lambda _query: {"results": {"bindings": rows}}


def test_a_renamed_series_reaches_the_russian_article_that_carries_its_imdb_id() -> None:
    """«Lioness» 2023 is «Спецназ: Львица»: the article names the first original.

    Names disagree, and «No description is available» on this card was a lie.  The
    article's Wikidata IMDb id equals the id the map filed under «Lioness», and that
    joins them; «Львица (телесериал)» with another id stays a namesake.
    """
    key, (found, _replies, answered) = _renamed_series(
        _imdb(Q116199566="tt13111078", Q1="tt0000001")
    )

    assert found[key][0] == "Спецназ: Львица"
    assert "Львица (телесериал)" not in found[key]
    assert answered == {key}


def test_a_silent_wikidata_leaves_the_renamed_series_unanswered_rather_than_empty() -> None:
    """Without the id check absence is not proven: no answered key, no week-long ``empty``."""

    def refuse(_query: str) -> Any:
        raise OSError("Wikidata is silent")

    key, (found, _replies, answered) = _renamed_series(refuse)

    assert key not in found
    assert answered == set()
