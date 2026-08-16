"""Проверяет контракт источника сведений и поведение его фейка."""

from tests.fakes.facts_source import FakeFactsSource
from torrcast.domain.movie_facts import MovieFacts
from torrcast.ports.facts_source import FactsSource


def test_fake_records_lookup_and_returns_facts() -> None:
    facts = MovieFacts("Тачки", "Cars", 2006)
    fake = FakeFactsSource(facts)
    port: FactsSource = fake
    assert port.lookup("Тачки", 2006) == facts
    assert fake.lookups == [("Тачки", 2006)]
