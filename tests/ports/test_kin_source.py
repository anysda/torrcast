"""Проверяет контракт источника родни картины и поведение его фейка."""

from tests.fakes.kin_source import FakeKinSource
from torrcast.domain.facts.kin import Kin
from torrcast.ports.kin_source import KinSource


def test_fake_answers_by_entity_and_records_that_it_was_asked() -> None:
    """Фейк отвечает по Q-идентификатору и помнит сам факт похода."""
    found = [Kin("Q105993", "Крепкий орешек 2", 1990)]
    fake = FakeKinSource(lambda entity, timeout: found if entity == "Q105598" else [])
    port: KinSource = fake
    assert port.kin("Q105598", 1.0) == found
    assert port.kin("Q1", 1.0) == []
    assert fake.asked == ["Q105598", "Q1"]


def test_a_silent_source_answers_with_an_empty_shelf() -> None:
    """Умолчание фейка - молчание Wikidata: родни нет, и это законный исход."""
    assert FakeKinSource().kin("Q1", 1.0) == []
