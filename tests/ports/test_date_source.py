"""Проверяет контракт второго источника года и поведение его фейка."""

from tests.fakes.date_source import FakeDateSource
from torrcast.ports.date_source import DateSource


def test_fake_answers_by_entity_and_records_that_it_was_asked() -> None:
    """Фейк отвечает по Q-идентификатору и помнит сам факт лишнего хопа."""
    fake = FakeDateSource(lambda entity, timeout: 2016 if entity == "Q2" else None)
    port: DateSource = fake
    assert port.published("Q2", 1.0) == 2016
    assert port.published("Q9", 1.0) is None
    assert fake.asked == ["Q2", "Q9"]


def test_a_silent_source_answers_none() -> None:
    """Умолчание фейка - молчание Wikidata: года нет, и это законный исход."""
    assert FakeDateSource().published("Q1", 1.0) is None
