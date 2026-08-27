"""Проверяет добор справки к меню: пакеты имён, порядок шагов и отказ украшений."""

import threading
import time
from typing import Any

import pytest

from tests import thread_guard
from tests.articles import CARS, MOANA, wiki_reply
from tests.fakes.json_client import FakeJsonClient
from tests.fakes.rating_dump import FakeRatingDump
from torrcast.adapters.wiki.endpoints import WIKIDATA_HOST
from torrcast.adapters.wiki.wiki_blurbs import WikiBlurbs
from torrcast.adapters.wiki.wiki_extracts import wiki_extracts
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.read_pages import _read_pages
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


def _extracts(
    client: FakeJsonClient, wanted: list[tuple[str, int | None]], timeout: float
) -> tuple[
    dict[tuple[str, int | None], str],
    dict[tuple[str, int | None], str],
    set[tuple[str, int | None]],
]:
    candidates, payload, answered = wiki_extracts(client, wanted, timeout)
    about, entities = _read_pages(payload, candidates)
    return about, entities, answered


def test_an_exact_offline_identity_restores_an_unyearred_blurb_and_rating() -> None:
    """Точное имя, год и тип IMDb подтверждают статью без года и несут оценку сами."""
    key = ("Матрица: Революция", 2003)
    article = (
        "«Матрица: Революция» (англ. The Matrix Revolutions) — американский "
        "научно-фантастический боевик, являющийся продолжением фильма «Матрица»."
    )

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == WIKIDATA_HOST:
            raise OSError("Wikidata молчит")
        return {
            "query": {
                "pages": [
                    {
                        "title": key[0],
                        "extract": article,
                        "pageprops": {"wikibase_item": "Q207536"},
                    }
                ]
            }
        }

    class Catalogue:
        @staticmethod
        def ids(
            pictures: list[tuple[str, int | None, str]],
        ) -> dict[tuple[str, int | None], str]:
            assert pictures == [(key[0], key[1], "movie")], "тип обязан доехать до карты"
            return {key: "tt0242653"}

    ready: list[dict[tuple[str, int | None], Fact]] = []
    found, answered = WikiBlurbs(
        FakeJsonClient(answer),
        FakeRatingDump(lambda: {"tt0242653": "6.7"}),
        Catalogue(),
    ).fetch([key], ready=ready.append, kinds={key: "movie"})

    assert ready == [{key: Fact(about=article, rating="IMDb 6.7")}]
    assert found[key] == Fact(about=article, rating="IMDb 6.7")
    assert answered == {key}


def test_one_request_carries_the_whole_franchise() -> None:
    """Все картины и все кандидаты уезжают одним запросом — их не по одному тянуть."""
    client = FakeJsonClient(lambda host, path, params: wiki_reply())
    about, _entities, answered = _extracts(client, [("Тачки", 2006), ("Моана", 2016)], 1.0)

    assert len(client.calls) == 1
    titles = client.calls[0][2]["titles"].split("|")
    assert titles[0] == "Тачки" and titles[1] == "Моана", "по кандидату на картину, потом вглубь"
    assert len(titles) <= _EXLIMIT, "лимит API на статьи в одном запросе"
    assert about[("Тачки", 2006)] == CARS
    assert about[("Моана", 2016)] == MOANA
    assert answered == {("Тачки", 2006), ("Моана", 2016)}, "про обе картины ответ приехал"


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

    about, entities, answered = _extracts(FakeJsonClient(answer), wanted, 1.0)

    assert len(asked) > 1, "имена должны уезжать несколькими пакетами"
    assert sum(len(part) for part in asked) > _EXLIMIT
    assert about[("Моана", 2016)] == MOANA, "уточнение «(мультфильм)» обязано быть спрошено"
    assert entities[("Моана", 2016)] == "Q1183953"
    assert ("Моана", 2016) in answered


def test_молчание_части_пакетов_не_читается_как_статьи_нет_про_её_картины() -> None:
    """🔴 TC-568. Ответ приехал неполным - и промолчавший пакет не говорит ничего.

    Неполный ответ считался полным, и картины, о которых просто не успели спросить,
    ложились в кэш как «статьи нет» на весь срок - хотя статья у них есть.
    """

    def deaf(host: str, path: str, params: dict[str, str]) -> Any:
        if "властелин" in params["titles"].split("|"):
            raise OSError("пакет промолчал")
        return wiki_reply()

    wanted: list[tuple[str, int | None]] = [("Тачки", 2006), ("Моана", 2016), ("Властелин", 2001)]
    about, _entities, answered = _extracts(FakeJsonClient(deaf), wanted, 1.0)

    assert about[("Тачки", 2006)] == CARS, "ответившая часть разбирается как обычно"
    assert answered == {("Тачки", 2006), ("Моана", 2016)}, (
        "«Властелин» не спрошен до конца - «статьи нет» про него нечестно"
    )


def test_молчание_всех_пакетов_это_отказ_сети_а_не_отсутствие_статьи() -> None:
    """Пустой ответ лёг бы в кэш на неделю и накрыл бы картину, известную Википедии."""
    tries: list[int] = []

    def broken(host: str, path: str, params: dict[str, str]) -> Any:
        tries.append(len(params["titles"].split("|")))
        raise OSError("сеть молчит")

    wanted: list[tuple[str, int | None]] = [(f"Картина {number}", 2000) for number in range(12)]

    try:
        _extracts(FakeJsonClient(broken), wanted, 1.0)
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
        if host == WIKIDATA_HOST:
            raise OSError("Wikidata молчит")
        return wiki_reply()

    out, answered = WikiBlurbs(FakeJsonClient(answer), FakeRatingDump()).fetch(
        [CARS_KEY], timeout=1.0
    )

    assert out[CARS_KEY].about == CARS, "описание добыто и отменять его нечем"
    assert not out[CARS_KEY].rating, "украшений нет - и это законный исход"
    assert answered == {CARS_KEY}


def test_описание_отдаётся_меню_до_того_как_спрошены_украшения() -> None:
    """Меню печатает то, что уже добыто, а не ждёт второго, более медленного шага."""
    order: list[str] = []

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        if host == WIKIDATA_HOST:
            order.append("украшения")
            return SPARQL
        return wiki_reply()

    def ready(part: dict[tuple[str, int | None], Fact]) -> None:
        order.append("описание")
        assert part[CARS_KEY].about == CARS

    ratings = FakeRatingDump(lambda: {"tt0317219": "7.2"})
    out, _answered = WikiBlurbs(FakeJsonClient(answer), ratings).fetch(
        [CARS_KEY], timeout=1.0, ready=ready
    )

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
        if host == WIKIDATA_HOST:
            return SPARQL
        order.append("вики-начало")
        time.sleep(0.3)
        order.append("вики-конец")
        return wiki_reply()

    blurbs = WikiBlurbs(FakeJsonClient(slow_wiki), FakeRatingDump(slow_scores))
    started = time.monotonic()
    out, _answered = blurbs.fetch([CARS_KEY], timeout=5.0)
    spent = time.monotonic() - started

    assert out[CARS_KEY].rating == "IMDb 7.2"
    # Оба шага стартовали до того, как кончился любой из них - значит шли вместе.
    assert order[:2] == ["рейтинги-начало", "вики-начало"]
    assert spent < 0.55


def test_the_batch_wave_is_closed_by_the_one_who_raised_it() -> None:
    """🔴 TC-723. Пакеты имён уезжают разом, и закрывает их тот же, кто поднял.

    Пакетов до трёх, и каждый едет своей ниткой. По сроку их бросали жить дальше:
    брошенная нитка доживает залипший запрос уже в чужой работе - в бою это показ, в
    прогоне соседняя проба, и красным там оказывается невиновный.

    Платит закрытие фоновый добор справки, который сюда и позвал: меню отпущено своим
    потолком задолго до этой секунды.
    """
    late = threading.Event()

    def slow(host: str, path: str, params: dict[str, str]) -> Any:
        late.wait(1.0)  # Википедия отвечает, но много позже отведённого срока
        return wiki_reply()

    before = thread_guard.alive()
    started = time.monotonic()

    with pytest.raises(OSError):  # ни один пакет не успел - это отказ сети, а не «статьи нет»
        _extracts(FakeJsonClient(slow), [CARS_KEY, ("Моана", 2016)], 0.05)

    left = thread_guard.alive() - before
    assert not left, f"нитки закрыл тот, кто их поднял, а живыми осталось {len(left)}: {left}"
    assert time.monotonic() - started >= 1.0, "отказ отдан после закрытия, а не вместо него"


def test_the_ratings_reader_is_closed_by_the_one_who_raised_it() -> None:
    """🔴 TC-723. Нитку чтения выгрузки оценок закрывает тот, кто её поднял.

    Выгрузка оценок читается рядом с первым запросом, отдельной ниткой, и по сроку её
    бросали дочитывать файл в чужой работе. Ждать её дольше срока незачем - рейтинг это
    украшение, - но закрыть за собой обязан тот, кто поднял.
    """
    late = threading.Event()

    def slow_dump() -> dict[str, str]:
        late.wait(1.0)  # выгрузка большая, первое чтение идёт долго
        return {"tt0317219": "7.2"}

    blurbs = WikiBlurbs(
        FakeJsonClient(lambda host, path, params: wiki_reply()), FakeRatingDump(slow_dump)
    )
    before = thread_guard.alive()
    started = time.monotonic()

    found, _answered = blurbs.fetch([CARS_KEY], 0.05)

    assert not found[CARS_KEY].rating, "оценка не успела к сроку - справка выходит без неё"
    left = thread_guard.alive() - before
    assert not left, f"нитку закрыл тот, кто её поднял, а живой осталась {left}"
    assert time.monotonic() - started >= 1.0, "справка отдана после закрытия, а не вместо него"
