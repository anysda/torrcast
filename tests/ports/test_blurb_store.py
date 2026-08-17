"""Проверяет контракт хранилища справки к меню и поведение его фейка."""

from tests.fakes.blurb_store import FakeBlurbStore
from torrcast.domain.facts.fact import Fact
from torrcast.ports.blurb_store import BlurbStore


def test_only_the_asked_pictures_come_back_and_misses_are_remembered() -> None:
    """Отдаётся только спрошенное, а пустой ответ помнится наравне с найденным."""
    fake = FakeBlurbStore()
    port: BlurbStore = fake
    cars = Fact(rating="IMDb 7.2")
    port.remember({("Тачки", 2006): cars}, [("Моана", 2016)])
    assert port.blurbs([("Тачки", 2006)]) == {("Тачки", 2006): cars}
    assert port.blurbs([("Моана", 2016)]) == {("Моана", 2016): Fact()}
    assert port.blurbs([("Дюна", 2021)]) == {}
    assert fake.remembered == [({("Тачки", 2006): cars}, [("Моана", 2016)])]
