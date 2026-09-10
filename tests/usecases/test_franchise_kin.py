"""Проверяет полку родни картины: паспорт даёт Q-идентификатор, кэш стоит перед сетью."""

from tests.fakes.kin_source import FakeKinSource
from tests.fakes.kin_store import FakeKinStore
from tests.fakes.passport import FakePassport
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.franchise_kin import FranchiseKin


def test_the_entity_from_the_passport_is_what_wikidata_gets_asked_about() -> None:
    """Полка спрашивает Wikidata по Q-идентификатору картины, а не по её имени."""
    passport = FakePassport({"Крепкий орешек": Origin(title="Die Hard", entity="Q105598")})
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found if entity == "Q105598" else [])

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())
    got = shelf.of("Крепкий орешек", False, 1.0)

    assert got == found
    assert kin.asked == ["Q105598"]


def test_a_picture_without_an_entity_never_reaches_wikidata() -> None:
    """Без Q-идентификатора спрашивать Wikidata не о чем - полка пуста без похода."""
    passport = FakePassport({"Неизвестное кино": Origin(title="Unknown")})
    kin = FakeKinSource()

    shelf = FranchiseKin(passport, kin, FakeKinStore(), FakePassport())
    assert shelf.of("Неизвестное кино", False, 1.0) == []
    assert kin.asked == []


def test_a_second_ask_for_the_same_picture_never_touches_the_network() -> None:
    """🔴 Второй заход за той же картиной не ходит в сеть - отвечает кэш на диске."""
    passport = FakePassport({"Крепкий орешек": Origin(title="Die Hard", entity="Q105598")})
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found)
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store, FakePassport())

    assert shelf.of("Крепкий орешек", False, 1.0) == found
    assert shelf.of("Крепкий орешек", False, 1.0) == found

    assert kin.asked == ["Q105598"], "второй заход обязан отвечать кэшем, а не сетью"


def test_a_franchise_without_kin_is_remembered_as_an_empty_shelf() -> None:
    """Пустой ответ тоже кэшируется - без этого каждый показ бил бы по сети заново."""
    passport = FakePassport({"Одинокое кино": Origin(title="Lonely", entity="Q1")})
    kin = FakeKinSource(lambda entity, timeout: [])
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store, FakePassport())

    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert kin.asked == ["Q1"]


def test_a_silent_network_leaves_no_row_in_the_cache() -> None:
    """🔴 Молчание сети не кладётся в кэш: ряд на диске переживёт и показ, и обновление.

    Разница с пустым ответом - вся суть: «родни нет» продукт узнал и отвечает списком,
    а «сеть молчит» не узнал ничего и отвечает ``None`` - незаконченным, чтобы следующий
    заход спросил заново. Замер 07-09-2026 на стенде `.104`: «Форсаж» лёг пустым рядом
    от одной оборванной связи и отвечал пусто за 0,0 с, пока живой запрос давал десять
    картин.
    """
    passport = FakePassport({"Форсаж": Origin(title="The Fast and the Furious", entity="Q1")})
    calls: list[str] = []

    def silence(entity: str, timeout: float) -> list[Kin]:
        calls.append(entity)
        raise OSError("HTTP 429")

    store = FakeKinStore()
    shelf = FranchiseKin(passport, FakeKinSource(silence), store, FakePassport())

    assert shelf.of("Форсаж", False, 1.0) is None
    assert store.written == [], "молчание сети записано в кэш пустой полкой"
    assert shelf.of("Форсаж", False, 1.0) is None
    assert calls == ["Q1", "Q1"], "второй заход обязан спросить сеть заново"


def test_a_degraded_passport_is_asked_again_live() -> None:
    """🔴 TC-1114. Паспорт офлайн-карты без Q-идентификатора переспрашивается живьём.

    Такой ряд ложится в кэш бессрочно в минуту молчания Википедии, и без переспроса
    полка глохла навсегда ещё до похода в Wikidata: замер 10-09-2026 на стенде `.104` -
    «Крепкий орешек» и «Форсаж» лежали в `facts.json` с пустым ``entity`` при живых
    сериях по четыре и десять картин.
    """
    cached = FakePassport({"Крепкий орешек": Origin(title="Die Hard", year=1988, source="map")})
    fresh = FakePassport(
        {"Крепкий орешек": Origin(title="Die Hard", year=1988, entity="Q105598", source="wiki")}
    )
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found)

    got = FranchiseKin(cached, kin, FakeKinStore(), fresh).of("Крепкий орешек", False, 1.0)

    assert got == found
    assert fresh.asked == ["Крепкий орешек"]
    assert kin.asked == ["Q105598"]


def test_a_wiki_passport_without_an_entity_is_not_reasked() -> None:
    """Статья прочитана, а Q-идентификатора у неё нет - переспрос того же ответа пуст."""
    passport = FakePassport({"Короткометражка": Origin(title="Short", source="wiki")})
    fresh = FakePassport()
    kin = FakeKinSource()

    got = FranchiseKin(passport, kin, FakeKinStore(), fresh).of("Короткометражка", False, 1.0)

    assert got == []
    assert fresh.asked == []
    assert kin.asked == []
