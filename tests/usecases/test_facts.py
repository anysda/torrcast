"""Проверяет сценарий справки к меню франшизы: кэш, дедлайн и дописывание после меню."""

import threading
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


def _found(_wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
    """Источник, которому есть что ответить: одна картина с рейтингом."""
    return {MOANA_KEY: Fact(rating="IMDb 7.6")}


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

    # Отмашкой, а не сном: нитку справки надо отпустить в конце пробы, иначе она
    # доживает своё молчание уже в среде соседа.
    stuck = threading.Event()

    def never(_wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        stuck.wait(30)
        return {}

    facts = _menu(FakeBlurbSource(never), FakeBlurbStore(), budget=0.3)
    facts.start()
    started = time.monotonic()

    try:
        assert facts.get("Моана", 2016) == Fact()
        assert time.monotonic() - started < 3.0
    finally:
        stuck.set()


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


def test_what_already_arrived_is_given_out_without_a_single_wait() -> None:
    """🔴 Меню справку не ждёт: спрашивает уже приехавшее и печатается немедленно.

    Одна картина меню лежит в кэше, вторая - нет: за ней ушёл добор, и его держат не
    отвечающим при бюджете в десять секунд. Дождись меню хоть чего-то из этого - и человек
    смотрел бы на пустой экран вместо списка.
    """
    held = threading.Event()

    def waiting(_wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        held.wait(10.0)
        return {}

    store = FakeBlurbStore({MOANA_KEY: Fact(rating="IMDb 7.6")})
    facts = Facts([MOANA_KEY, CARS_KEY], 10.0, store=store, source=FakeBlurbSource(waiting))
    facts.start()
    started = time.monotonic()

    assert facts.ready("Моана", 2016) == Fact(rating="IMDb 7.6")
    assert facts.ready("Тачки", 2006) == Fact(), "не приехавшее - пустая справка, а не ожидание"
    assert not facts._done.is_set(), "добор ещё идёт - и ровно его меню больше не ждёт"
    assert time.monotonic() - started < 0.5, "ждать тут нечего и незачем"
    held.set()


def test_the_arrival_of_the_reference_is_told_to_whoever_is_watching() -> None:
    """Приехавшую справку показанное меню узнаёт звонком, а не опросом по кругу.

    Опрос стоил бы интерпретатора тем самым сетевым пробам, которые справку и добывают.
    """
    seen: list[Fact] = []
    facts = _menu(FakeBlurbSource(_found), FakeBlurbStore())
    facts.watch(lambda: seen.append(facts.ready("Моана", 2016)))
    facts.start()
    facts.finish()

    assert Fact(rating="IMDb 7.6") in seen


def test_a_watcher_that_broke_does_not_bring_down_the_top_up() -> None:
    """Смотрящий упал - добор дописывает кэш дальше: справка не вправе ронять показ."""

    def broken() -> None:
        raise RuntimeError("экран уехал")

    store = FakeBlurbStore()
    facts = _menu(FakeBlurbSource(_found), store)
    facts.watch(broken)
    facts.start()
    facts.finish()

    assert store.stored == {MOANA_KEY: Fact(rating="IMDb 7.6")}, "итог всё равно лёг в кэш"


def test_nobody_is_told_anything_after_the_menu_let_the_reference_go() -> None:
    """Отписка обязана работать: меню ушло с экрана, и писать в чужой вывод нельзя."""
    seen: list[str] = []
    facts = _menu(FakeBlurbSource(_found), FakeBlurbStore())
    facts.watch(lambda: seen.append("звонок"))
    facts.watch(None)
    facts.start()
    facts.finish()

    assert seen == []


def test_the_deadline_lets_the_menu_go_but_the_topup_thread_is_closed_by_its_owner() -> None:
    """🔴 TC-723. Дедлайн отпускает МЕНЮ, а поток закрывает тот, кто его поднял.

    Приём «подняли, подождали по сроку, бросили» тут не лежит, и это надо держать, а не
    помнить: срок ждёт не поток, а событие (:meth:`Facts.wait`), и меню уходит печататься
    ровно по нему. Поток же закрывается :meth:`Facts.finish` - её зовут в ``finally`` обе
    команды, и опоздавшая справка успевает лечь в кэш, чтобы СЛЕДУЮЩЕЕ меню было полным.

    Сторож потоков (:mod:`tests.thread_guard`) видит тут ровно то, что должен: после
    пробы не осталось ничего живого. Без закрытия поток дописывал бы кэш уже в чужой
    работе - в бою в показе, в прогоне в соседней пробе.
    """

    def late(_wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        time.sleep(1.0)  # источник отвечает много позже потолка меню
        return {MOANA_KEY: Fact(rating="IMDb 7.6")}

    store = FakeBlurbStore()
    facts = _menu(FakeBlurbSource(late), store, budget=0.1)
    facts.start()
    started = time.monotonic()
    facts.wait()
    menu = time.monotonic() - started

    assert menu < 0.5, f"меню отпущено по своему потолку, а ждало {menu:.2f} с"
    assert facts.ready("Моана", 2016) == Fact(), "к потолку меню справка не приехала"

    facts.finish()

    assert store.stored[MOANA_KEY].rating == "IMDb 7.6", "опоздавшая справка легла в кэш"


def test_the_menu_is_let_go_by_the_blurbs_and_not_by_the_ornaments() -> None:
    """🔴 TC-717. Ожидание меню кончается на ОПИСАНИЯХ, а не на всей справке.

    Описание приезжает первым шагом добора (медиана 0.73 с), рейтинг с хронометражем -
    вторым, вдвое более медленным. Дописать в показанный список можно только второе,
    поэтому ждут ровно первое: источник тут отдал описания и залип на украшениях, и меню
    обязано уйти печататься сразу, а не досиживать свой потолок.
    """
    ornaments = threading.Event()

    def stepwise(wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        ornaments.wait(10.0)
        return {}

    source = FakeBlurbSource(stepwise)
    facts = Facts([MOANA_KEY], 10.0, store=FakeBlurbStore(), source=source)
    facts.start()
    facts._ready({MOANA_KEY: Fact(about=MOANA)})
    started = time.monotonic()

    try:
        facts.wait_about()
        told = time.monotonic() - started

        assert told < 0.5, f"описания на руках, а меню ждало ещё {told:.2f} с"
        assert facts.ready("Моана", 2016).about == MOANA
        assert not facts._done.is_set(), "второй шаг ещё едет - и ровно его меню не ждёт"
    finally:
        ornaments.set()
        facts.finish()


def test_a_reference_with_nothing_to_say_holds_the_menu_not_a_moment() -> None:
    """Справка молчит - ждать нечего: список выходит сразу, а не досиживает потолок.

    Три вида молчания, и все три обязаны стоить ноль: спрашивать было некого, всё лежало в
    кэше, источник ответил отказом. Потолок :data:`FACTS_BUDGET` - потолок, а не срок.
    """

    def dead(_wanted: list[tuple[str, int | None]]) -> Any:
        raise OSError("сети нет")

    empty = Facts([], 10.0, store=FakeBlurbStore(), source=FakeBlurbSource())
    cached = _menu(FakeBlurbSource(), FakeBlurbStore({MOANA_KEY: Fact(about=MOANA)}), budget=10.0)
    refused = _menu(FakeBlurbSource(dead), FakeBlurbStore(), budget=10.0)

    started = time.monotonic()
    for facts in (empty, cached, refused):
        facts.start()
        facts.wait_about()
        facts.finish()
    held = time.monotonic() - started

    assert held < 1.0, f"молчание не стоит ожидания, а меню просидело {held:.2f} с"
    assert cached.ready("Моана", 2016).about == MOANA
    assert refused.ready("Моана", 2016) == Fact()
