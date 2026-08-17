"""Проверяет контракт источника статей и поведение его фейка."""

from tests.fakes.article_source import FakeArticleSource
from torrcast.domain.facts.origin import Origin
from torrcast.ports.article_source import ArticleSource


def test_fake_answers_and_records_the_question() -> None:
    """Фейк отвечает заданным паспортом и помнит, о чём и с каким сроком спросили."""
    paper = Origin(title="Cars", year=2006, name="Тачки")
    fake = FakeArticleSource(lambda title, series, timeout: paper)
    port: ArticleSource = fake
    assert port.look("Тачки", False, 1.2) == paper
    assert fake.calls == [("Тачки", False, 1.2)]


def test_a_silent_source_answers_an_empty_passport() -> None:
    """Умолчание фейка - молчание источника: пустой паспорт, а не исключение."""
    assert FakeArticleSource().look("Тачки", False, 1.2) == Origin()
