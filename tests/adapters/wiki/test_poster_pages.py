"""Проверяет приговор постера: у какой находки есть английская статья со сверенным годом.

🔴 Отрицательная проба на шитую правку живёт тут же
(:func:`test_a_namesake_of_another_year_gets_no_article_at_all`): сними сверку года - и
краснеет она утверждением о ПОВЕДЕНИИ, а не отсутствием имени в модуле.
"""

from __future__ import annotations

from typing import Any

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import EN_WIKI_HOST, WIKI_HOST, WIKIDATA_HOST
from torrcast.adapters.wiki.poster_pages import PosterPages
from torrcast.domain.facts.ask import Ask

#: Русский раздел так и держит эту находку: имя с годом - перенаправление на имя без него.
PARASITE = {
    "title": "Паразиты (фильм)",
    "langlinks": [{"lang": "en", "title": "Parasite (2019 film)"}],
    "pageprops": {"wikibase_item": "Q61448040"},
    "categories": [
        {"title": "Категория:Фильмы 2019 года"},
        {"title": "Категория:Фильмы Республики Корея"},
    ],
}
MATRIX = {
    "title": "Матрица (фильм)",
    "langlinks": [{"lang": "en", "title": "The Matrix"}],
    "pageprops": {"wikibase_item": "Q83495"},
    "categories": [{"title": "Категория:Фильмы 1999 года"}],
}


def _wiki(
    pages: list[dict[str, Any]],
    redirects: list[dict[str, str]] | None = None,
    english: list[dict[str, Any]] | None = None,
    years: dict[str, str] | None = None,
) -> FakeJsonClient:
    """Википедия и Wikidata, отвечающие каждая своим ответом."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == WIKIDATA_HOST:
            return {
                "results": {
                    "bindings": [
                        {
                            "item": {"value": f"http://www.wikidata.org/entity/{entity}"},
                            "date": {"value": date},
                        }
                        for entity, date in (years or {}).items()
                        if f"wd:{entity}" in params["query"]
                    ]
                }
            }
        if host == EN_WIKI_HOST:
            return {"query": {"pages": list(english or ())}}
        asked = set(params.get("titles", "").split("|"))
        return {
            "query": {
                "redirects": [hop for hop in (redirects or ()) if hop["from"] in asked],
                "pages": [page for page in pages if page["title"] in asked],
            }
        }

    return FakeJsonClient(answer)


def test_a_namesake_of_another_year_gets_no_article_at_all() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на сверку года: сними её - и обе находки получат статью.

    Живой случай: пять находок «Паразиты» разных лет вели в одну статью 2019 года и
    получали ОДИН постер с одним отпечатком. Картинка чужой картины подписана нашей
    строкой, и отличить её человеку нечем, поэтому у тёзки чужого года статьи нет
    вовсе - строка остаётся строкой.
    """
    client = _wiki(
        [PARASITE],
        redirects=[{"from": "Паразиты (фильм, 2019)", "to": "Паразиты (фильм)"}],
    )
    pages = PosterPages(client)
    wanted = pages.wanted([Ask("Паразиты", 2019, "movie"), Ask("Паразиты", 1999, "movie")], 1.0)

    assert wanted[Ask("Паразиты", 2019, "movie")] == ["Parasite (2019 film)"]
    assert wanted[Ask("Паразиты", 1999, "movie")] == [], "тёзке 1999 года досталась чужая статья"


def test_a_series_does_not_take_the_article_of_the_film_of_the_same_year() -> None:
    """Год у них один, и без рода в список приезжали две строки с ОДНОЙ картинкой."""
    client = _wiki([PARASITE])
    wanted = PosterPages(client).wanted([Ask("Паразиты", 2019, "tv")], 1.0)
    assert wanted[Ask("Паразиты", 2019, "tv")] == []


def test_the_whole_list_is_judged_in_one_or_two_requests() -> None:
    """🔴 Приговора ждёт человек перед списком: три запроса на находку - это секунды.

    Имена всего списка уезжают одной выборкой, а год добирается одним общим SPARQL.
    """
    client = _wiki([PARASITE, MATRIX])
    asks = [Ask("Паразиты", 2019, "movie"), Ask("Матрица", 1999, "movie")]
    wanted = PosterPages(client).wanted(asks, 1.0)

    assert wanted[asks[0]] == ["Parasite (2019 film)"]
    assert wanted[asks[1]] == ["The Matrix"]
    assert len(client.calls) == 1, f"на две находки ушло запросов: {len(client.calls)}"


def test_a_year_that_no_category_names_is_asked_of_wikidata_in_one_batch() -> None:
    """Категории отвечают даром, а SPARQL стоит похода - и идёт он один на весь список."""
    quiet = {**PARASITE, "categories": [{"title": "Категория:Фильмы Республики Корея"}]}
    client = _wiki([quiet], years={"Q61448040": "2019-05-21"})
    wanted = PosterPages(client).wanted([Ask("Паразиты", 2019, "movie")], 1.0)

    assert wanted[Ask("Паразиты", 2019, "movie")] == ["Parasite (2019 film)"]
    assert [call[0] for call in client.calls].count(WIKIDATA_HOST) == 1


def test_the_english_article_is_reached_by_the_original_name_when_there_is_no_russian_one() -> None:
    """«Армитаж: Двойная матрица» лежит в английском разделе ровно под оригинальным именем.

    Русское имя ведёт при этом в статью соседки 1994 года, которую сверка и отсекает.
    """
    client = _wiki(
        [],
        english=[
            {
                "title": "Armitage: Dual Matrix",
                "pageprops": {"wikibase_item": "Q42"},
                "categories": [{"title": "Категория:Фильмы 2002 года"}],
            }
        ],
    )
    ask = Ask("Армитаж: Двойная матрица", 2002, "movie", "Armitage: Dual Matrix")
    assert PosterPages(client).wanted([ask], 1.0)[ask] == ["Armitage: Dual Matrix"]
    assert any(call[0] == EN_WIKI_HOST for call in client.calls)


def test_a_silent_wikipedia_is_not_the_same_as_a_picture_without_an_article() -> None:
    """🔴 Отказ сети наверх поднимается: проглоти его - и картина осталась бы без постера.

    Выглядело бы это честным «статьи не нашлось», а на деле это 429 на одном заходе.
    """

    def refuse(host: str, path: str, params: dict[str, str]) -> Any:
        raise OSError(f"{WIKI_HOST} ответил 429")

    try:
        PosterPages(FakeJsonClient(refuse)).wanted([Ask("Тачки", 2006, "movie")], 1.0)
    except OSError as bad:
        assert "429" in str(bad)
    else:
        raise AssertionError("отказ сети проглочен и выдан за «статьи нет»")
