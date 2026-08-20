"""Проверяет режим «оба типа»: согласие двух путей и второй источник года."""

import threading
import time

from tests.fakes.date_source import FakeDateSource
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP, SOURCE_WIKI
from torrcast.usecases.passport_either import PassportEither


def test_an_unknown_type_is_trusted_only_when_film_and_series_agree() -> None:
    """Тип неизвестен (пустая выдача) - пробуем оба, но верим лишь согласию.

    Спека требует подсказывать тип, а на пустой выдаче его взять неоткуда. Наугад нельзя:
    неверный тип уводит в чужую статью.
    """

    def deadwood(title: str, series: bool, budget: float) -> Origin:
        # Фильм 2006 против сериала 2004 - это разные картины, наугад не выдаём.
        if series:
            return Origin(title="Deadwood", year=2004, name="Дедвуд")
        return Origin(title="Deadwood: The Movie", year=2006, name="Дедвуд")

    assert PassportEither(deadwood, FakeDateSource()).of("Дедвуд") == Origin(), (
        "фильм и сериал разошлись - молчим"
    )

    def climbers(title: str, series: bool, budget: float) -> Origin:
        # С неверным типом «Восхождение» уводит в чужой сериал «Hunyadi» 2024.
        if series:
            return Origin(title="Hunyadi", year=2024, name="Восхождение ворона")
        return Origin(title="The Ascent", year=1976, name="Восхождение")

    assert PassportEither(climbers, FakeDateSource()).of("Восхождение") == Origin(), (
        "чужая статья из неверного типа - не паспорт"
    )

    def agreeing(title: str, series: bool, budget: float) -> Origin:
        return Origin(title="Cars", year=2006, name="Тачки")

    agreed = PassportEither(agreeing, FakeDateSource()).of("Тачки")
    assert agreed.title == "Cars", "оба сошлись на одной картине - паспорт есть"


def test_a_lone_answer_lends_its_name_but_never_its_year() -> None:
    """Ответил один путь из двух - это не согласие, а единственное мнение. Год ему не верим.

    «Атака титанов»: статьи об аниме-сериале в русской Википедии нет вовсе, и на оба
    вопроса приезжает одна и та же статья японского игрового фильма. Гейт типа отдаёт её
    только вопросу про фильм, вопрос про сериал остаётся без ответа - и прежнее правило
    «ответил один - его и берём» уверенно подписывало аниме-сериал 2013 года чужим 2015.

    Имя и год у такого ответа стоят разного: имя ``Attack on Titan`` у фильма и сериала
    общее, а год объявлен сильнее выдачи. Отдаём имя, молчим про год.
    """
    lone = Origin(title="Attack on Titan", year=2015, name="Атака титанов")

    def only_movie(title: str, series: bool, budget: float) -> Origin:
        return Origin() if series else lone

    found = PassportEither(only_movie, FakeDateSource()).of("Атака титанов")

    assert found.title == "Attack on Titan", "имя общее у фильма и сериала - добору годится"
    assert found.name == "Атака титанов", "русское имя тоже: по нему добор ищет обратно"
    assert found.year is None, "год у сериала 2013, а не 2015 - неподтверждённый не отдаём"


def test_a_lone_year_is_kept_only_when_a_second_source_confirms_it() -> None:
    """🔴 TC-134. Одинокий год отдаём, лишь если его подтверждает P577; иначе - только имя.

    Совпала дата первой публикации с годом статьи - год двух источников отдаём, разошлась
    или Wikidata молчит - МОЛЧИМ (только имя), а не выбираем «поудачнее».
    """
    p577: dict[str, int | None] = {"Q1": 1960, "Q2": 2016, "Q3": 2008, "Q4": 1999, "Q5": None}
    dates = FakeDateSource(lambda entity, timeout: p577.get(entity))
    # имя -> (паспорт статьи с Q-идентификатором, ожидаемый год итога)
    table = {
        "Психо": (Origin("Psycho", 1960, "Психо", "Q1"), 1960),  # 1960 == 1960 -> год
        "Моана": (Origin("Moana", 2016, "Моана", "Q2"), 2016),  # 2016 == 2016 -> год
        "Во все тяжкие": (Origin("Breaking Bad", 2008, "Во все тяжкие", "Q3"), 2008),  # -> год
        "Оно": (Origin("It", 2014, "Оно", "Q4"), None),  # P577 1999 != 2014 -> молчим
        "Медведь": (Origin("The Bear", 2026, "Медведь", "Q5"), None),  # Wikidata молчит
    }
    for name, (paper, want) in table.items():

        def lone(title: str, series: bool, budget: float, paper: Origin = paper) -> Origin:
            return Origin() if series else paper

        got = PassportEither(lone, dates).of(name)
        assert got.title == paper.title, f"{name}: имя одинокого ответа остаётся всегда"
        assert got.year == want, f"{name}: год статьи {paper.year}, P577 {p577[paper.entity]}"


def test_a_lone_answer_without_a_wikidata_id_never_asks_for_a_second_source() -> None:
    """🔴 TC-134. Нет Q-идентификатора - второго источника нет: год роняем, P577 не трогаем.

    Латинописанное аниме русская Википедия отдаёт без ``wikibase_item``, и спросить P577
    нечем. Хоп стоит времени до меню, поэтому его и не делаем.
    """
    dates = FakeDateSource(lambda entity, timeout: 2015)
    lone = Origin("Attack on Titan", 2015, "Атака титанов")  # entity == ""
    either = PassportEither(lambda title, series, budget: Origin() if series else lone, dates)

    found = either.of("Атака титанов")

    assert found.title == "Attack on Titan", "имя остаётся - справка не замолкает"
    assert found.year is None, "без второго источника год неподтверждён"
    assert dates.asked == [], "без Q-идентификатора P577 не спрашиваем - лишний хоп ни к чему"


def test_отброшенный_год_карты_не_числится_за_ней_в_отметке() -> None:
    """🔴 TC-450. Отметка описывает ОТДАННЫЙ паспорт, а не путь, которым его собирали.

    Вскрылось живым прогоном по 101 имени: у трёх ответов стояло «wiki+map», а года в них
    не было вовсе. Поверх статьи карта даёт ровно год, и режим «оба типа» у одинокого
    ответа этот год отбирает - вклад карты обнулялся, а в отметке она оставалась.
    """
    lone = Origin(title="The Hobbit", year=1977, name="Хоббит", source="wiki+map")
    either = PassportEither(
        lambda title, series, budget: Origin() if series else lone, FakeDateSource()
    )

    found = either.of("хоббит")

    assert found.title == "The Hobbit"
    assert found.year is None, "одинокий ответ год отдаёт только со вторым источником"
    assert found.source == SOURCE_WIKI, "года нет - и заслуги карты в ответе нет"


def test_the_last_source_of_a_lone_answer_is_never_crossed_out() -> None:
    """Карта ОДНА и назвала имя - потеря года её из отметки не вычёркивает."""
    lone = Origin(title="Brat 2", year=2000, name="Брат 2", source=SOURCE_MAP)
    either = PassportEither(
        lambda title, series, budget: Origin() if series else lone, FakeDateSource()
    )

    found = either.of("брат 2")

    assert found.title == "Brat 2"
    assert found.source == SOURCE_MAP, "имя дала карта - она и источник"


def test_both_types_together_fit_into_one_budget_not_two() -> None:
    """🔴 TC-243. Бюджет режима «оба типа» - СРОК на весь поход, а не мерка на каждый шаг.

    Одинокий ответ отправлялся за подтверждением года ко второму источнику со своим полным
    бюджетом СВЕРХ уже потраченного, и режим стоил вдвое дороже обещанного. Здесь оба пути
    отвечают на исходе срока, а Wikidata молчит дольше, чем его осталось: правильный ответ
    - вернуться в срок БЕЗ года.
    """
    budget = 1.0
    lone = Origin("Moana", 2016, "Моана", "Q1")

    def slow_paper(title: str, series: bool, spent: float) -> Origin:
        time.sleep(budget * 0.8)  # оба пути уложились в срок, но съели почти весь
        return Origin() if series else lone

    # Отмашкой, а не сном: поток второго источника надо отпустить в конце пробы,
    # иначе он доживает свой срок уже в среде соседа.
    stuck = threading.Event()

    def slow_wikidata(entity: str, timeout: float) -> int:
        stuck.wait(budget)  # остатка срока на второй источник уже нет
        return 2016

    either = PassportEither(slow_paper, FakeDateSource(slow_wikidata))
    started = time.monotonic()
    try:
        found = either.of("Моана", budget=budget)
        elapsed = time.monotonic() - started

        assert found.title == "Moana", "имя одинокого ответа остаётся - справка не замолкает"
        assert found.year is None, "второй источник не успел - год неподтверждён, и мы молчим"
        assert elapsed < budget * 1.4, f"обещали {budget} с, ушло {elapsed:.2f} с"
    finally:
        stuck.set()
