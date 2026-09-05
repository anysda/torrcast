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
from torrcast.domain.facts.dated import Dated


def _named(rows: list[Dated]) -> list[str]:
    """Английские имена отобранных статей: приговор отдаёт строки, а не имена."""
    return [row.page for row in rows]


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
#: Полнометражная антология: имя статьи голое, потому что делить его не с кем.
ANIMATRIX = {
    "title": "Аниматрица",
    "langlinks": [{"lang": "en", "title": "The Animatrix"}],
    "pageprops": {"wikibase_item": "Q219776"},
    "categories": [{"title": "Категория:Мультфильмы 2003 года"}],
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

    assert _named(wanted[Ask("Паразиты", 2019, "movie")]) == ["Parasite (2019 film)"]
    assert wanted[Ask("Паразиты", 1999, "movie")] == [], "тёзке 1999 года досталась чужая статья"


def test_a_series_does_not_take_the_article_of_the_film_of_the_same_year() -> None:
    """Год у них один, и без рода в список приезжали две строки с ОДНОЙ картинкой.

    🔴 Судится тут ЦЕПОЧКА, а не сверка рода поодиночке, и разница живая: выборка статьи
    от рода не зависит вовсе (замер TC-1050), поэтому «спросить второй раз другим родом»
    открывает не новую статью, а ровно эту же - ту, которую первый проход честно отверг.
    Модульная проверка рода такую починку пропустила бы зелёной.
    """
    client = _wiki([PARASITE])
    wanted = PosterPages(client).wanted([Ask("Паразиты", 2019, "tv")], 1.0)
    assert wanted[Ask("Паразиты", 2019, "tv")] == []


def test_an_anthology_with_episode_marks_gets_the_article_of_its_own_film() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на догадку о роде: сверяй один род - и антология без постера.

    «Аниматрица» - полнометражный фильм из новелл, и раздача несёт метки серий; род
    «сериал» ставит по ним разбор имени раздачи, а не содержание картины. Отменяет догадку
    имя статьи: у «Аниматрицы» оно голое, тёзки-сериала на свете нет, и статья под ним -
    её собственная. У «Паразитов» имя разведено самим разделом, и там догадка остаётся.
    """
    client = _wiki([ANIMATRIX])
    ask = Ask("Аниматрица", 2003, "tv")
    wanted = PosterPages(client).wanted([ask], 1.0)

    assert _named(wanted[ask]) == ["The Animatrix"], "антологии отказано в её же статье"
    assert len(client.calls) == 1, f"на догадку ушёл лишний поход: {len(client.calls)}"


def test_the_whole_list_is_judged_in_one_or_two_requests() -> None:
    """🔴 Приговора ждёт человек перед списком: три запроса на находку - это секунды.

    Имена всего списка уезжают одной выборкой, а год добирается одним общим SPARQL.
    """
    client = _wiki([PARASITE, MATRIX])
    asks = [Ask("Паразиты", 2019, "movie"), Ask("Матрица", 1999, "movie")]
    wanted = PosterPages(client).wanted(asks, 1.0)

    assert _named(wanted[asks[0]]) == ["Parasite (2019 film)"]
    assert _named(wanted[asks[1]]) == ["The Matrix"]
    assert len(client.calls) == 1, f"на две находки ушло запросов: {len(client.calls)}"


def test_a_year_that_no_category_names_is_asked_of_wikidata_in_one_batch() -> None:
    """Категории отвечают даром, а SPARQL стоит похода - и идёт он один на весь список."""
    quiet = {**PARASITE, "categories": [{"title": "Категория:Фильмы Республики Корея"}]}
    client = _wiki([quiet], years={"Q61448040": "2019-05-21"})
    wanted = PosterPages(client).wanted([Ask("Паразиты", 2019, "movie")], 1.0)

    assert _named(wanted[Ask("Паразиты", 2019, "movie")]) == ["Parasite (2019 film)"]
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
    assert _named(PosterPages(client).wanted([ask], 1.0)[ask]) == ["Armitage: Dual Matrix"]
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


#: Догадки полнотекстового поиска: столько же, сколько отвод сверки года
#: (:data:`~torrcast.adapters.wiki.poster_pages._TRIED`), и ни одна из них не картина.
GUESSES = [
    {"title": "Ли, Брюс", "categories": [{"title": "Категория:Родившиеся в 1940 году"}]},
    {"title": "Ын Сиюнь", "categories": [{"title": "Категория:Родившиеся в 1944 году"}]},
    {"title": "События октября 1993 года", "categories": [{"title": "Категория:1993 год"}]},
    {"title": "Аведон, Лорен", "categories": [{"title": "Категория:Родившиеся в 1962 году"}]},
]
#: Она же под оригинальным именем: год свой не называет, его знает только Wikidata.
BLOOD_BROTHERS = {
    "title": "No Retreat, No Surrender 3: Blood Brothers",
    "pageprops": {"wikibase_item": "Q776037"},
    "categories": [{"title": "Category:1990 American films"}],
}


def _guessing(english: list[dict[str, Any]], years: dict[str, str]) -> FakeJsonClient:
    """Русский раздел, у которого прямая выборка пуста, а поиск отдаёт мимо картины."""

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == WIKIDATA_HOST:
            return {
                "results": {
                    "bindings": [
                        {
                            "item": {"value": f"http://www.wikidata.org/entity/{entity}"},
                            "date": {"value": date},
                        }
                        for entity, date in years.items()
                        if f"wd:{entity}" in params["query"]
                    ]
                }
            }
        if host == EN_WIKI_HOST:
            return {"query": {"pages": english}}
        if params.get("generator") == "search":
            return {"query": {"pages": GUESSES}}
        return {"query": {"pages": []}}

    return FakeJsonClient(answer)


def test_the_article_under_the_original_name_outranks_the_guesses_of_full_text_search() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на порядок доверия: поставь догадки вперёд - и постера нет.

    Живой случай «Не отступать и не сдаваться 3: Братья по крови» 1990 года: русской
    статьи нет вовсе, английская лежит ровно под оригинальным именем и год её
    подтверждает Wikidata, а полнотекстовый поиск отдаёт четыре догадки - Брюса Ли,
    Ын Сиюня, октябрь 1993-го и Лорена Аведона. Догадок ровно столько же, сколько
    статей доходит до сверки года, и стоя впереди они занимали отвод целиком.
    """
    client = _guessing([BLOOD_BROTHERS], {"Q776037": "1990-01-01T00:00:00Z"})
    ask = Ask(
        "Не отступать и не сдаваться 3: Братья по крови",
        1990,
        "movie",
        "No Retreat, No Surrender 3: Blood Brothers",
    )

    wanted = PosterPages(client).wanted([ask], 1.0)

    assert _named(wanted[ask]) == ["No Retreat, No Surrender 3: Blood Brothers"], (
        "статью с точным оригинальным именем вытеснили догадки поиска"
    )


#: Она же римской цифрой: раздел держит статью ТОЛЬКО под этим именем.
POLTERGEIST = {
    "title": "Poltergeist II: The Other Side",
    "pageprops": {"wikibase_item": "Q1057668"},
    "categories": [{"title": "Category:1986 supernatural films"}],
}


def test_the_english_section_is_asked_for_the_roman_form_of_the_part_number() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА: спроси одну форму - и статьи под римской цифрой нет.

    Живой случай «Полтергейст 2: Обратная сторона» 1986 года: русской статьи нет,
    полнотекстовый поиск отдаёт четыре чужие страницы, а английская статья лежит под
    именем «Poltergeist II: The Other Side» - и никогда под арабской двойкой, которой
    раздача пишет номер части. Раздел тут отвечает только на римскую форму, поэтому
    спроси его одной арабской - и картины не станет. Обе формы едут одним ``titles``,
    так что второе имя не стоит ни одного лишнего похода в сеть.
    """
    roman = "Poltergeist II: The Other Side"

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == WIKIDATA_HOST:
            return {
                "results": {
                    "bindings": [
                        {
                            "item": {"value": "http://www.wikidata.org/entity/Q1057668"},
                            "date": {"value": "1986-05-23T00:00:00Z"},
                        }
                    ]
                }
            }
        if host == EN_WIKI_HOST:
            asked = params.get("titles", "").split("|")
            return {"query": {"pages": [POLTERGEIST] if roman in asked else []}}
        if params.get("generator") == "search":
            return {"query": {"pages": GUESSES}}
        return {"query": {"pages": []}}

    client = FakeJsonClient(answer)
    ask = Ask("Полтергейст 2: Обратная сторона", 1986, "movie", "Poltergeist 2: The Other Side")

    wanted = PosterPages(client).wanted([ask], 1.0)

    assert _named(wanted[ask]) == [roman], "у английского раздела спросили одну арабскую форму"


#: Русская статья своей картины: год выхода 2001, а раздача расширенной версии несёт 2011.
FELLOWSHIP = {
    "title": "Властелин колец: Братство кольца",
    "langlinks": [{"lang": "en", "title": "The Lord of the Rings: The Fellowship of the Ring"}],
    "pageprops": {"wikibase_item": "Q127367"},
    "categories": [{"title": "Категория:Фильмы 2001 года"}],
}
#: Мультфильм 1994 года: его английская статья лежит ровно под именем римейка.
LION_1994 = {
    "title": "Король Лев",
    "langlinks": [{"lang": "en", "title": "The Lion King"}],
    "pageprops": {"wikibase_item": "Q36479"},
    "categories": [{"title": "Категория:Мультфильмы 1994 года"}, {"title": "Категория:Фильмы"}],
}
#: Своя статья римейка 2019 года: имя английской с уточнением, а не голое.
LION_2019 = {
    "title": "Король Лев (мультфильм, 2019)",
    "langlinks": [{"lang": "en", "title": "The Lion King (2019 film)"}],
    "pageprops": {"wikibase_item": "Q29579"},
    "categories": [{"title": "Категория:Фильмы 2019 года"}],
}


def test_a_release_that_carries_the_year_of_a_reissue_still_finds_its_own_article() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на разбор перевыпуска: сними его - и статьи нет вовсе.

    Живой случай «Властелин колец: Братство кольца»: расширенная версия выходит
    отдельной раздачей и пишет год издания, 2011, а статья держит год выхода, 2001.
    Пока годы сверялись одним членством в списке, находка оставалась без обложки при
    живой статье своей собственной картины.
    """
    client = _wiki([FELLOWSHIP])
    ask = Ask(
        "Властелин колец: Братство кольца",
        2011,
        "movie",
        "The Lord of the Rings: The Fellowship of the Ring",
    )

    wanted = PosterPages(client).wanted([ask], 1.0)

    assert _named(wanted[ask]) == ["The Lord of the Rings: The Fellowship of the Ring"], (
        "год перевыпуска оставил картину без её собственной статьи"
    )


def test_a_remake_of_the_same_original_name_does_not_take_the_older_picture() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА на границу разбора перевыпуска: сними пустоту первого
    захода - и «Король Лев» 2019 года получит картинку мультфильма 1994-го.

    Оригинальное имя у них одно и то же, «The Lion King», и точное совпадение имени
    сработало бы на старой статье. Держит римейк не признак строки, а то, что своя
    статья у него есть: перевыпуском он не был.
    """
    client = _wiki([LION_1994, LION_2019])
    ask = Ask("Король Лев", 2019, "movie", "The Lion King")

    wanted = PosterPages(client).wanted([ask], 1.0)

    assert _named(wanted[ask]) == ["The Lion King (2019 film)"], (
        "римейку досталась статья старого мультфильма"
    )
