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
        names = {"Avatar": ["Аватар"], "The Muse": ["Муза"]}
        return {(title, year): names[title] for title, year, _kind in pictures}


def test_a_latin_tile_reads_its_russian_release_name_when_the_article_is_that_picture() -> None:
    """Поиск по ``Avatar фильм`` не приносит «Аватар» 2009 года; карта IMDb знает имя.

    Голое имя - статья про индуизм или про муз, «Аватар (фильм)» называет чужой оригинал,
    и их адреса в кандидаты не попадают. Заглушка «Муза (фильм)» оригинала не называет
    вовсе, и её выделяет уточнение.
    """
    avatar, muse = ("Avatar", 2009), ("The Muse", 1999)
    pages = {
        "Аватар": "Авата́р \u2014 термин индуизма; фильм 2009 года тоже назван так.",
        "Аватар (фильм)": "«Аватар» (англ. Cyber Wars) \u2014 фильм 2009 года.",
        "Аватар (фильм, 2009)": "«Авата́р» (англ. Avatar) \u2014 американский фильм 2009 года.",
        "Муза": "Музы \u2014 богини; кинофильм 1999 года назван так же.",
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
        [avatar, muse],
        1.0,
        {avatar: "movie", muse: "movie"},
        names=_Names(),
    )

    assert found == {avatar: ["Аватар (фильм, 2009)"], muse: ["Муза (фильм)"]}
    assert len(replies) == 4
    assert answered == {avatar, muse}
