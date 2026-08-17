"""Проверяет добор справки к меню: пакеты имён, порядок шагов и отказ украшений."""

import time
from typing import Any

from tests.articles import CARS, MOANA, wiki_reply
from tests.fakes.json_client import FakeJsonClient
from tests.fakes.rating_dump import FakeRatingDump
from torrcast.adapters.wiki.endpoints import _WIKIDATA_HOST
from torrcast.adapters.wiki.wiki_blurbs import WikiBlurbs
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import _EXLIMIT

CARS_KEY = ("Тачки", 2006)
#: Ответ Wikidata на пару «идентификатор IMDb, хронометраж» для «Тачек».
SPARQL = {
    "results": {
        "bindings": [
            {
                "item": {"value": "http://www.wikidata.org/entity/Q182153"},
                "imdb": {"value": "tt0317219"},
                "dur": {"value": "117"},
            }
        ]
    }
}


def test_one_request_carries_the_whole_franchise() -> None:
    """Все картины и все кандидаты уезжают одним запросом — их не по одному тянуть."""
    client = FakeJsonClient(lambda host, path, params: wiki_reply())
    blurbs = WikiBlurbs(client, FakeRatingDump())

    about, _entities = blurbs.extracts([("Тачки", 2006), ("Моана", 2016)], 1.0)

    assert len(client.calls) == 1
    titles = client.calls[0][2]["titles"].split("|")
    assert titles[0] == "Тачки" and titles[1] == "Моана", "по кандидату на картину, потом вглубь"
    assert len(titles) <= _EXLIMIT, "лимит API на статьи в одном запросе"
    assert about[("Тачки", 2006)] == CARS
    assert about[("Моана", 2016)] == MOANA


def test_кандидаты_картин_уезжают_несколькими_пакетами_а_не_обрезаются() -> None:
    """🔴 TC-561. В запрос влезает двадцать имён, а у меню их под сотню.

    Лишние кандидаты просто отбрасывались, и это стоило не времени, а самой справки:
    «Моана» лежит под уточнением «(мультфильм)», а до Википедии доезжало по два-три
    имени на картину.
    """
    asked: list[list[str]] = []

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        names = params["titles"].split("|")
        asked.append(names)
        # Википедия отвечает только про то, о чём спросили: не уехало имя - нет и статьи.
        pages = [
            {
                "title": "Моана (мультфильм)",
                "extract": MOANA,
                "pageprops": {"wikibase_item": "Q1183953"},
            }
        ]
        return {"query": {"pages": [page for page in pages if page["title"] in names]}}

    # Меню, в котором уточнение «Моаны» стоит за двадцатым именем.
    wanted: list[tuple[str, int | None]] = [(f"Картина {number}", 2000) for number in range(12)]
    wanted.append(("Моана", 2016))

    about, entities = WikiBlurbs(FakeJsonClient(answer), FakeRatingDump()).extracts(wanted, 1.0)

    assert len(asked) > 1, "имена должны уезжать несколькими пакетами"
    assert sum(len(part) for part in asked) > _EXLIMIT
    assert about[("Моана", 2016)] == MOANA, "уточнение «(мультфильм)» обязано быть спрошено"
    assert entities[("Моана", 2016)] == "Q1183953"


def test_молчание_всех_пакетов_это_отказ_сети_а_не_отсутствие_статьи() -> None:
    """Пустой ответ лёг бы в кэш на неделю и накрыл бы картину, известную Википедии."""
    tries: list[int] = []

    def broken(host: str, path: str, params: dict[str, str]) -> Any:
        tries.append(len(params["titles"].split("|")))
        raise OSError("сеть молчит")

    wanted: list[tuple[str, int | None]] = [(f"Картина {number}", 2000) for number in range(12)]

    try:
        WikiBlurbs(FakeJsonClient(broken), FakeRatingDump()).extracts(wanted, 1.0)
    except OSError:
        assert len(tries) > 1, "молчание должно быть проверено на нескольких пакетах"
        return
    raise AssertionError("отказ сети обязан быть исключением, а не пустым ответом")


def test_отказ_украшений_не_отнимает_уже_добытое_описание() -> None:
    """🔴 TC-561. Wikidata несёт рейтинг и хронометраж, описание несёт Википедия.

    Опоздание украшений отменяло описание целиком - исключение улетало наверх, и в кэш не
    ложилось ничего. Тридцать восемь прогонов из ста не сохранили ни строки.
    """

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == _WIKIDATA_HOST:
            raise OSError("Wikidata молчит")
        return wiki_reply()

    out = WikiBlurbs(FakeJsonClient(answer), FakeRatingDump()).fetch([CARS_KEY], timeout=1.0)

    assert out[CARS_KEY].about == CARS, "описание добыто и отменять его нечем"
    assert not out[CARS_KEY].rating, "украшений нет - и это законный исход"


def test_описание_отдаётся_меню_до_того_как_спрошены_украшения() -> None:
    """Меню печатает то, что уже добыто, а не ждёт второго, более медленного шага."""
    order: list[str] = []

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == _WIKIDATA_HOST:
            order.append("украшения")
            return SPARQL
        return wiki_reply()

    def ready(part: dict[tuple[str, int | None], Fact]) -> None:
        order.append("описание")
        assert part[CARS_KEY].about == CARS

    ratings = FakeRatingDump(lambda: {"tt0317219": "7.2"})
    out = WikiBlurbs(FakeJsonClient(answer), ratings).fetch([CARS_KEY], timeout=1.0, ready=ready)

    assert order == ["описание", "украшения"], "описание отдаётся первым, а не после всего"
    assert out[CARS_KEY].rating == "IMDb 7.2"
    assert out[CARS_KEY].runtime == "1 ч 57 мин"


def test_the_ratings_dump_is_read_alongside_the_first_request_not_after_it() -> None:
    """Выгрузка рейтингов - файл, а не сеть: внутри дедлайна она идёт параллельно запросу.

    Третьим шагом её сотня тысяч строк ложилась на те же полторы секунды, что и оба
    запроса, и справка не успевала к меню на ровном месте.
    """
    order: list[str] = []

    def slow_scores() -> dict[str, str]:
        order.append("рейтинги-начало")
        time.sleep(0.3)
        order.append("рейтинги-конец")
        return {"tt0317219": "7.2"}

    def slow_wiki(host: str, path: str, params: dict[str, str]) -> Any:
        if host == _WIKIDATA_HOST:
            return SPARQL
        order.append("вики-начало")
        time.sleep(0.3)
        order.append("вики-конец")
        return wiki_reply()

    blurbs = WikiBlurbs(FakeJsonClient(slow_wiki), FakeRatingDump(slow_scores))
    started = time.monotonic()
    out = blurbs.fetch([CARS_KEY], timeout=5.0)
    spent = time.monotonic() - started

    assert out[CARS_KEY].rating == "IMDb 7.2"
    # Оба шага стартовали до того, как кончился любой из них - значит шли вместе.
    assert order[:2] == ["рейтинги-начало", "вики-начало"]
    assert spent < 0.55
