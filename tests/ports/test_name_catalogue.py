"""Проверяет контракт офлайн-карты имён и поведение её фейка."""

from tests.fakes.name_catalogue import FakeNameCatalogue
from torrcast.domain.facts.origin import Origin
from torrcast.ports.name_catalogue import NameCatalogue


def test_fake_answers_and_records_that_it_was_asked() -> None:
    """Фейк помнит имена, за которыми в карту всё-таки сходили."""
    found = Origin(title="American Factory", year=2019)
    fake = FakeNameCatalogue(lambda title, series: found)
    port: NameCatalogue = fake
    assert port.look("Американская фабрика", False) == found
    assert fake.asked == ["Американская фабрика"]


def test_an_untouched_catalogue_keeps_its_log_empty() -> None:
    """Никто не спрашивал - и в журнале пусто: на этом стоят проверки лишних чтений."""
    assert FakeNameCatalogue().asked == []
