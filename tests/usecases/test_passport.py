"""Проверяет сценарий паспорта: кэш, статья, офлайн-карта и потолок по времени."""

import threading
import time
from dataclasses import replace
from typing import Any

from tests import thread_guard
from tests.fakes.article_source import FakeArticleSource
from tests.fakes.date_source import FakeDateSource
from tests.fakes.name_catalogue import FakeNameCatalogue
from tests.fakes.origin_store import FakeOriginStore
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP, SOURCE_WIKI
from torrcast.usecases.passport import Passport


def _passport(
    articles: FakeArticleSource | None = None,
    catalogue: FakeNameCatalogue | None = None,
    store: FakeOriginStore | None = None,
    dates: FakeDateSource | None = None,
) -> Passport:
    return Passport(
        articles or FakeArticleSource(),
        catalogue or FakeNameCatalogue(),
        store or FakeOriginStore(),
        dates or FakeDateSource(),
    )


def test_a_stored_passport_is_answered_without_asking_anyone() -> None:
    """Со второго показа справку не спрашивают вовсе - отвечает кэш."""
    stored = Origin(title="Cars", year=2006, source=SOURCE_WIKI)
    articles = FakeArticleSource()
    passport = _passport(articles, store=FakeOriginStore({("Тачки", False): stored}))

    assert passport.of("Тачки", False, 1.0) == stored
    assert articles.calls == []


def test_origin_yields_empty_when_the_reference_raises() -> None:
    """Справка (Википедия/Wikidata) отвечает ошибкой - паспорт пуст, поиск не падает."""

    def dead(title: str, series: bool, timeout: float) -> Origin:
        raise OSError("getaddrinfo: сети нет")

    # Ключевое: НЕ исключение наружу, а пустой паспорт. Иначе упал бы весь поиск.
    assert _passport(FakeArticleSource(dead)).of("Восхождение") == Origin()


def test_origin_never_blocks_past_budget_when_the_reference_hangs() -> None:
    """Справка молчит (залипший сокет) - паспорт уходит по бюджету, а не держит поиск."""

    # Отмашкой, а не сном: поток справки надо отпустить в конце пробы, иначе он
    # доживает свой залипший сокет уже в среде соседа.
    stuck = threading.Event()

    def never(title: str, series: bool, timeout: float) -> Origin:
        stuck.wait(30)
        return Origin(title="Ascension")

    started = time.monotonic()
    try:
        found = _passport(FakeArticleSource(never)).of("Восхождение", budget=0.3)
        elapsed = time.monotonic() - started

        assert found == Origin(), "залипшая справка не должна протащить свой ответ"
        assert elapsed < 3.0, "паспорт обязан вернуться по бюджету, а не ждать сокет"
    finally:
        stuck.set()


def test_справка_называет_источник_каждого_ответа() -> None:
    """🔴 TC-450. Ответ есть - видно и КЕМ он дан: иначе пользу карты нечем сосчитать.

    Валовое покрытие («у стольких-то запросов оригинал нашёлся») не отвечает на вопрос,
    ради которого карта имён и заведена: скольким из них тот же оригинал уже дала бы одна
    Википедия. Отметка источника разводит три случая, и они стоят разного.
    """

    def answers(paper: Origin, catalogue: Origin) -> Passport:
        return _passport(
            FakeArticleSource(lambda title, series, timeout: paper),
            FakeNameCatalogue(lambda title, series: catalogue),
        )

    wiki = answers(Origin(title="Psycho", year=1960, name="Психо"), Origin())
    assert wiki.of("Психо", False, 1.0).source == SOURCE_WIKI

    only_map = answers(Origin(), Origin(title="Cars", year=2006, name="Тачки")).of(
        "Тачки", False, 1.0
    )
    assert only_map.title == "Cars"
    assert only_map.source == SOURCE_MAP, "статьи нет вовсе - это заслуга карты"

    both = answers(
        Origin(title="Serial Experiments Lain", name="Эксперименты Лэйн"), Origin(year=1998)
    ).of("Эксперименты Лэйн", True, 1.0)
    assert both.year == 1998
    assert both.source == "wiki+map", "имя дала статья, год дописала карта - названы оба"


def test_a_guessed_name_is_not_given_a_year_from_the_offline_map() -> None:
    """🔴 TC-493. Догадке справки год из карты не подставляется - и карта за неё не читается.

    Карта отвечает на ТОЧНОЕ имя, а догадка означает ровно обратное: имя, которым спросили,
    статья не носит. Сложи их в один паспорт - выйдет имя одной картины с годом другой, а
    год объявлен сильнее выдачи.
    """
    catalogue = FakeNameCatalogue(
        lambda title, series: Origin(title="Serial Experiments Lain", year=1998)
    )
    guessed = Origin(title="Serial Experiments Lain", name="Эксперименты Лэйн", guessed=True)
    guess = _passport(FakeArticleSource(lambda title, series, timeout: guessed), catalogue).of(
        "эксперименты лейн", True, budget=1.0
    )

    assert guess.title == "Serial Experiments Lain"
    assert guess.year is None, "год точного имени не годится картине, названной по сходству"
    assert catalogue.asked == [], "за годом для догадки в карту не ходят вовсе"

    named = replace(guessed, guessed=False)
    sure = _passport(FakeArticleSource(lambda title, series, timeout: named), catalogue).of(
        "Эксперименты Лэйн", True, budget=1.0
    )

    assert sure.year == 1998, "своё имя статья носит - год карты ему годится"
    assert catalogue.asked == ["Эксперименты Лэйн"]


def test_the_map_supplies_the_year_an_article_does_not_name() -> None:
    """Имя статьи и год офлайн-каталога складываются в один паспорт."""
    article = Origin(title="Brother", name="Брат", entity="Q1192679")
    found = _passport(
        FakeArticleSource(lambda title, series, timeout: article),
        FakeNameCatalogue(lambda title, series: Origin(title="Brat", year=1997, name="Брат")),
    ).of("Брат", False, budget=1.0)

    assert (found.title, found.year, found.entity) == ("Brother", 1997, "Q1192679")


def test_a_slow_offline_map_never_pushes_the_passport_past_the_budget() -> None:
    """🔴 TC-493. Год из карты дописывается только в остаток срока, а не поверх него.

    Разбор карты стоит полсекунды на первое обращение, и лежала она поверх уже
    потраченного: статью находили в срок, а паспорт с её годом приезжал после потолка.
    """

    def slow_map(title: str, series: bool) -> Origin:
        time.sleep(0.5)  # первое чтение файла
        return Origin(year=1998)

    passport = _passport(
        FakeArticleSource(lambda title, series, timeout: Origin(title="Serial Experiments Lain")),
        FakeNameCatalogue(slow_map),
    )
    start = time.monotonic()
    found = passport.of("Эксперименты Лэйн", True, budget=0.15)
    took = time.monotonic() - start

    assert found.title == "Serial Experiments Lain", "готовый паспорт карта отнять не вправе"
    assert took < 0.4, f"потолок обещан, а справка шла {took:.2f} с"


def test_the_map_answers_when_wikipedia_misses_the_deadline() -> None:
    """Медленная страница значений не отнимает картину, известную офлайн-каталогу."""

    def slow_article(title: str, series: bool, timeout: float) -> Origin:
        time.sleep(0.1)
        return Origin()

    found = _passport(
        FakeArticleSource(slow_article),
        FakeNameCatalogue(
            lambda title, series: Origin(title="American Factory", year=2019, name=title)
        ),
    ).of("Американская фабрика", False, budget=0.01)

    assert (found.title, found.year) == ("American Factory", 2019)


def test_the_likeness_mark_survives_the_cache_and_the_both_types_mode() -> None:
    """Отметка «имя лишь похоже» доезжает и до кэша, и через режим «оба типа».

    Без кэша гейт добора на втором показе той же картины поверил бы догадке как
    доказанному имени, а без режима «оба типа» - на первом же.
    """
    guess = Origin(title="Nous sommes tous des assassins", name="Все мы убийцы", guessed=True)
    store = FakeOriginStore()
    passport = _passport(
        FakeArticleSource(lambda title, series, timeout: Origin() if series else guess),
        store=store,
    )

    lone = passport.of("Все мы незнакомцы", None, 1.0)

    assert lone.guessed, "режим «оба типа» отметку не теряет"
    assert store.read("Все мы незнакомцы", None) == replace(guess, source=SOURCE_WIKI)


def test_the_both_types_mode_uses_only_its_own_cache_key() -> None:
    """Внутренние пробы фильма и сериала не становятся ответами на запрос с типом."""
    found = Origin(title="Serial Experiments Lain", year=1998, name="Эксперименты Лэйн")
    store = FakeOriginStore()
    passport = _passport(FakeArticleSource(lambda title, series, timeout: found), store=store)

    wiki = replace(found, source=SOURCE_WIKI)
    assert passport.of("Эксперименты Лэйн", None, budget=1.0) == wiki
    assert store.read("Эксперименты Лэйн", None) == wiki
    assert store.read("Эксперименты Лэйн", False) is None
    assert store.read("Эксперименты Лэйн", True) is None


def test_a_typed_answer_is_written_to_the_cache_under_its_type() -> None:
    """Ответ с подсказанным типом ложится в свой ряд и второй раз сети не стоит."""
    article = FakeArticleSource(
        lambda title, series, timeout: Origin(title="Cars", year=2006, name="Тачки")
    )
    store = FakeOriginStore()
    passport = _passport(article, store=store)

    first = passport.of("Тачки", False, 1.0)
    second = passport.of("Тачки", False, 1.0)

    assert first == second
    assert len(article.calls) == 1, "второй раз в сеть не ходим"
    assert [title for title, _series, _found in store.written] == ["Тачки"]


def test_an_empty_passport_is_never_written_to_the_cache() -> None:
    """Молчание в кэш не ложится: сеть могла и просто не ответить."""
    store = FakeOriginStore()
    empty: Any = _passport(store=store).of("Никому не известное", False, 1.0)

    assert not empty
    assert store.written == []


def test_one_name_is_asked_by_one_thread_no_matter_how_many_ask() -> None:
    """🔴 TC-723. Поток тут один на ИМЯ, а не на запрос, и опоздавший ответ не пропадает.

    Срок отпускает спрашивающего, но оборвать поток, залипший в системном вызове, нечем -
    он живёт дальше и доживает своё уже в показе, а в прогоне красит ложным красным
    соседнюю пробу. Ждать его закрытия здесь нельзя: по сроку отвечают ЧЕЛОВЕКУ, и потолок
    ожидания справки продуктовый. Значит, мера тут - число потоков, и её спрашивает сторож
    (:mod:`tests.thread_guard`).

    Второй спрос про то же имя не заводит второго похода: он ждёт тот же поток, и ответ,
    опоздавший к первому сроку, достаётся ему даром.
    """
    asked = 0

    def slow(title: str, series: bool, timeout: float) -> Origin:
        nonlocal asked
        asked += 1
        # Второго похода за тем же именем быть не должно, и его поток обязан пережить
        # пробу: иначе сторож не увидит того, ради чего стоит.
        time.sleep(2.0 if asked > 1 else 0.4)
        return Origin(title="Ascension", year=1976)

    passport = _passport(FakeArticleSource(slow))
    before = thread_guard.alive()

    assert passport.of("Восхождение", False, budget=0.05) == Origin(), "в срок не приехало"
    found = passport.of("Восхождение", False, budget=1.0)

    assert found.title == "Ascension", "опоздавший ответ достался следующему спросившему"
    assert asked == 1, f"поход за именем один, а было их {asked}"
    left = thread_guard.alive() - before
    assert not left, f"поток на имя один, и он закрыт, а живыми осталось {len(left)}: {left}"


def test_a_slow_map_is_read_by_one_thread_no_matter_how_many_ask() -> None:
    """🔴 TC-723. Разбор карты - один поток на имя: второй спрос заводил второй разбор.

    Карта читается один раз на процесс, но поток под неё заводился на каждый спрос: не
    уложившийся в срок оставался жить, а следующий спрашивающий поднимал ещё один.
    """
    asked = 0

    def slow_map(title: str, series: bool) -> Origin:
        nonlocal asked
        asked += 1
        # Второго разбора того же файла быть не должно, и его поток обязан пережить пробу.
        time.sleep(2.0 if asked > 1 else 0.4)
        return Origin(year=1998)

    passport = _passport(catalogue=FakeNameCatalogue(slow_map))
    before = thread_guard.alive()

    assert not passport._catalogued("Эксперименты Лэйн", True, 0.05), "в срок не приехало"
    found = passport._catalogued("Эксперименты Лэйн", True, 1.0)

    assert found.year == 1998, "опоздавший год достался следующему спросившему"
    assert asked == 1, f"разбор карты один, а было их {asked}"
    left = thread_guard.alive() - before
    assert not left, f"поток на имя один, и он закрыт, а живыми осталось {len(left)}: {left}"
