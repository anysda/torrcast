"""Проверяет синхронный поход в Википедию за паспортом картины."""

import threading
import time
from typing import Any

from tests import thread_guard
from tests.articles import LAIN, page, wiki_reply
from tests.fakes.date_source import FakeDateSource
from tests.fakes.json_client import FakeJsonClient
from tests.fakes.name_catalogue import FakeNameCatalogue
from tests.fakes.origin_store import FakeOriginStore
from torrcast.adapters.wiki.wiki_articles import WikiArticles
from torrcast.adapters.wiki.wiki_spelling import WikiSpelling
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.passport import Passport


def _articles(client: FakeJsonClient, catalogue: FakeNameCatalogue) -> WikiArticles:
    return WikiArticles(client, WikiSpelling(client), catalogue)


def test_an_article_answer_is_never_overridden_by_the_map() -> None:
    """Статья нашлась - карта не спрашивается вовсе: она последний шаг, а не поправка."""

    def wiki(host: str, path: str, params: dict[str, str]) -> Any:
        if params.get("generator"):  # поиск и подсказки сюда не доходят
            raise AssertionError("статья нашлась прямой выборкой - поиск не нужен")
        return wiki_reply()

    catalogue = FakeNameCatalogue(lambda title, series: Origin(title="Wrong Title", year=1900))
    found = _articles(FakeJsonClient(wiki), catalogue).look("Тачки", False, 1.0)

    assert found.title == "Cars"
    assert found.year == 2006
    assert catalogue.asked == [], "карта не нужна ответившей статье"


def test_the_map_answers_when_wikipedia_does_not_know_the_name() -> None:
    """Все шаги Википедии промолчали - паспорт приходит из офлайн-карты, без сети."""
    silent = FakeJsonClient(lambda host, path, params: {"query": {"pages": []}})
    catalogue = FakeNameCatalogue(
        lambda title, series: Origin(title="American Factory", year=2019, name=title)
    )

    found = _articles(silent, catalogue).look("Американская фабрика", False, 1.0)

    assert (found.title, found.year) == ("American Factory", 2019)
    assert catalogue.asked == ["Американская фабрика"]


def test_a_series_asks_for_its_own_qualified_article_first() -> None:
    """У сериала своя статья, и лежит она под своим уточнением - его и спрашиваем раньше."""
    client = FakeJsonClient(lambda host, path, params: {"query": {"pages": []}})
    _articles(client, FakeNameCatalogue()).look("Дедвуд", True, 1.0)

    names = client.calls[0][2]["titles"].split("|")
    assert "сериал" in names[0], f"первым спрошено {names[0]}"


def test_a_name_spelled_otherwise_is_answered_within_the_same_budget() -> None:
    """🔴 TC-493. Написание имени не решает, доедет ли оригинал: кругов по сети два, не три.

    Живой заход: «Эксперименты Лэйн» лежат ровно под своим заголовком, прямая выборка
    отвечает первым же кругом, и добор по ``Serial Experiments Lain`` приносит 48 раздач.
    То же аниме, набранное строчными и через «лейн», под заголовком не лежит: выборка
    молчит, поиск Википедии молчит тоже, и знает ответ только разбор описки. Пока он шёл
    ТРЕТЬИМ кругом, в потолок справки эта очередь не влезала - человек читал «ничего не
    нашлось» о картине, которую справка отлично знает.

    Здесь каждый круг стоит треть потолка: очередь из трёх не уложится, волна из двух
    уложится. Проверяется именно результат в срок, а не порядок вызовов.
    """
    round_trip = 0.3
    lain = page("Эксперименты Лэйн", LAIN, english="Serial Experiments Lain")

    def wiki(host: str, path: str, params: dict[str, str]) -> Any:
        time.sleep(round_trip)
        if params.get("generator") == "prefixsearch":  # подсказчик знает написание
            return {"query": {"pages": [lain]}}
        return {"query": {"pages": []}}

    articles = _articles(FakeJsonClient(wiki), FakeNameCatalogue())
    passport = Passport(articles, FakeNameCatalogue(), FakeOriginStore(), FakeDateSource())

    found = passport.of("эксперименты лейн", True, budget=round_trip * 2.5)

    assert found.title == "Serial Experiments Lain", "имя знает подсказчик, и оно обязано доехать"
    assert found.guessed, "имя лишь признано похожим - паспорт обязан это сказать"


def test_the_two_step_wave_is_closed_by_the_one_who_raised_it() -> None:
    """🔴 TC-723. Выборка по имени закрывает за собой обе нитки второго шага.

    Поиск и разбор описки идут разом, каждый своей ниткой, и по сроку их бросали жить
    дальше. Брошенная нитка доживает свой залипший запрос в чужой работе - в бою это
    показ, в прогоне соседняя проба, и красным там оказывается невиновный.

    Платит закрытие фоновая нитка паспорта, которая сюда и позвала: потолок ожидания
    справки держит она, и от закрытия он не сдвигается.
    """
    late = threading.Event()

    def slow(host: str, path: str, params: dict[str, str]) -> Any:
        late.wait(1.0)  # Википедия отвечает, но много позже отведённого срока
        return {"query": {"pages": []}}

    articles = _articles(FakeJsonClient(slow), FakeNameCatalogue())
    before = thread_guard.alive()
    started = time.monotonic()

    articles.look("Восхождение", False, 0.05)

    left = thread_guard.alive() - before
    assert not left, f"нитки закрыл тот, кто их поднял, а живыми осталось {len(left)}: {left}"
    assert time.monotonic() - started >= 1.0, "ответ отдан после закрытия, а не вместо него"
