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

    got = FranchiseKin(passport, kin, FakeKinStore()).of("Крепкий орешек", False, 1.0)

    assert got == found
    assert kin.asked == ["Q105598"]


def test_a_picture_without_an_entity_never_reaches_wikidata() -> None:
    """Без Q-идентификатора спрашивать Wikidata не о чем - полка пуста без похода."""
    passport = FakePassport({"Неизвестное кино": Origin(title="Unknown")})
    kin = FakeKinSource()

    assert FranchiseKin(passport, kin, FakeKinStore()).of("Неизвестное кино", False, 1.0) == []
    assert kin.asked == []


def test_a_second_ask_for_the_same_picture_never_touches_the_network() -> None:
    """🔴 Второй заход за той же картиной не ходит в сеть - отвечает кэш на диске."""
    passport = FakePassport({"Крепкий орешек": Origin(title="Die Hard", entity="Q105598")})
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    kin = FakeKinSource(lambda entity, timeout: found)
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store)

    assert shelf.of("Крепкий орешек", False, 1.0) == found
    assert shelf.of("Крепкий орешек", False, 1.0) == found

    assert kin.asked == ["Q105598"], "второй заход обязан отвечать кэшем, а не сетью"


def test_a_franchise_without_kin_is_remembered_as_an_empty_shelf() -> None:
    """Пустой ответ тоже кэшируется - без этого каждый показ бил бы по сети заново."""
    passport = FakePassport({"Одинокое кино": Origin(title="Lonely", entity="Q1")})
    kin = FakeKinSource(lambda entity, timeout: [])
    store = FakeKinStore()
    shelf = FranchiseKin(passport, kin, store)

    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert shelf.of("Одинокое кино", False, 1.0) == []
    assert kin.asked == ["Q1"]
