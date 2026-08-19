"""Проверяет сценарий справки к меню франшизы: кэш, дедлайн и дописывание после меню."""

import time
from typing import Any

from tests.articles import CARS, MOANA
from tests.fakes.blurb_source import FakeBlurbSource
from tests.fakes.blurb_store import FakeBlurbStore
from torrcast.domain.facts.fact import Fact
from torrcast.usecases.facts import Facts

MOANA_KEY = ("Моана", 2016)
CARS_KEY = ("Тачки", 2006)


def _menu(source: FakeBlurbSource, store: FakeBlurbStore, budget: float = 5.0) -> Facts:
    return Facts([MOANA_KEY], budget, store=store, source=source)


def test_a_silent_source_leaves_the_menu_exactly_as_it_was() -> None:
    """Источник лёг — меню печатается прежней строкой и не ждёт ни секунды.

    Это и есть главное ограждение справки: она украшение, а не механизм показа.
    """

    def dead(_wanted: list[tuple[str, int | None]]) -> Any:
        raise OSError("сети нет")

    facts = _menu(FakeBlurbSource(dead), FakeBlurbStore(), budget=0.5)
    facts.start()

    assert facts.get("Моана", 2016) == Fact()


def test_the_menu_never_waits_longer_than_its_budget() -> None:
    """Источник молчит (не отвечает вовсе) — меню уходит по бюджету, а не висит."""

    def never(_wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        time.sleep(30)
        return {}

    facts = _menu(FakeBlurbSource(never), FakeBlurbStore(), budget=0.3)
    facts.start()
    started = time.monotonic()

    assert facts.get("Моана", 2016) == Fact()
    assert time.monotonic() - started < 3.0


def test_the_network_answer_does_not_throw_away_what_the_cache_had() -> None:
    """Сеть отвечает про ненайденное - и не вправе стирать уже найденное.

    Присваиванием ``self.found = fetch(...)`` кэшированная справка выбрасывалась: в меню
    из четырёх картин оставалась ровно та, про которую ответила сеть.
    """
    store = FakeBlurbStore({CARS_KEY: Fact(rating="IMDb 7.2")})
    source = FakeBlurbSource(lambda wanted: {("Тачки 2", 2011): Fact(rating="IMDb 6.2")})
    facts = Facts([CARS_KEY, ("Тачки 2", 2011)], 5.0, store=store, source=source)
    facts.start()
    facts.finish()

    assert facts.get("Тачки", 2006).rating == "IMDb 7.2"
    assert facts.get("Тачки 2", 2011).rating == "IMDb 6.2"
    assert source.walks == [[("Тачки 2", 2011)]], "про лежащее в кэше в сеть не ходят"


def test_an_empty_answer_is_remembered_so_the_walk_is_not_repeated() -> None:
    """Источник ответил, а сказать ему нечего - это тоже ответ, и он помнится.

    Раньше пустой ряд в кэш не попадал вовсе: каждое меню шло за ним в сеть заново, не
    успевало к дедлайну и печаталось голым - и следующее ровно так же.
    """
    store = FakeBlurbStore()
    source = FakeBlurbSource(lambda wanted: {CARS_KEY: Fact(rating="IMDb 7.2")})
    wanted = [CARS_KEY, ("Тачки: Мультачки. Байки Мэтра", 2008)]

    first = Facts(wanted, 5.0, store=store, source=source)
    first.start()
    assert first.get("Тачки", 2006).rating == "IMDb 7.2"
    first.finish()

    second = Facts(wanted, 5.0, store=store, source=source)
    second.start()
    assert second.get("Тачки", 2006).rating == "IMDb 7.2"
    assert second.get("Тачки: Мультачки. Байки Мэтра", 2008) == Fact()
    # Второй заход в сеть не пошёл: пустота лежит в кэше наравне с найденным.
    assert len(source.walks) == 1


def test_a_half_heard_answer_is_not_remembered_as_no_article() -> None:
    """🔴 TC-568. Про промолчавшую часть ответа «статьи нет» - выдумка, в кэш ей нельзя.

    Справка спрашивается пакетами разом; часть ответила, часть промолчала - и картины из
    молчащей части ложились в кэш пустыми на весь срок, хотя статья у них есть. Один
    неудачный момент делал картину без рейтинга и хронометража надолго.
    """
    store = FakeBlurbStore()
    source = FakeBlurbSource(
        lambda wanted: {CARS_KEY: Fact(rating="IMDb 7.2")}, unanswered={MOANA_KEY}
    )
    wanted = [CARS_KEY, MOANA_KEY]

    first = Facts(wanted, 5.0, store=store, source=source)
    first.start()
    first.finish()

    assert store.remembered == [({CARS_KEY: Fact(rating="IMDb 7.2")}, [])], (
        "«Моана» не ложится в кэш как «статьи нет»: про неё просто не ответили"
    )

    second = Facts(wanted, 5.0, store=store, source=source)
    second.start()
    second.finish()
    assert len(source.walks) == 2, "за «Моаной» ходят снова - её справка ещё не добыта"


def test_a_menu_with_nothing_to_ask_never_starts_a_walk() -> None:
    """Пустая франшиза и полный кэш одинаково не стоят ни одного похода в сеть."""
    source = FakeBlurbSource()
    empty = Facts([], 5.0, store=FakeBlurbStore(), source=source)
    empty.start()
    assert empty.get("Моана", 2016) == Fact()

    full = _menu(source, FakeBlurbStore({MOANA_KEY: Fact(about=MOANA)}))
    full.start()
    assert full.get("Моана", 2016).about == MOANA
    assert source.walks == []


def test_a_half_ready_answer_never_covers_what_is_already_known() -> None:
    """В кэш ложится итог, а не полуфабрикат: лежащее слева уступает тому, что уже есть."""
    store = FakeBlurbStore()
    source = FakeBlurbSource(lambda wanted: {CARS_KEY: Fact(about=CARS, rating="IMDb 7.2")})
    facts = Facts([CARS_KEY], 5.0, store=store, source=source)
    facts.start()
    facts.finish()

    facts._ready({CARS_KEY: Fact(about=CARS)})

    assert facts.get("Тачки", 2006).rating == "IMDb 7.2"
    assert store.remembered == [({CARS_KEY: Fact(about=CARS, rating="IMDb 7.2")}, [])]
