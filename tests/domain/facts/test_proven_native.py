"""Проверяет признак отечественной картины: доказано справкой, а не выведено из пустоты."""

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.proven_native import proven_native


def test_a_read_article_without_a_foreign_name_proves_the_picture_is_ours() -> None:
    """Статья прочитана, чужого имени в ней нет - вот теперь это отечественная картина."""
    assert proven_native(Origin(name="Брат", year=1997, native=True), "Брат")


def test_an_empty_original_alone_proves_nothing() -> None:
    """🔴 TC-567. Пустой оригинал без доказательства - это «мы не спросили», а не «нет его».

    Тем же пустым полем кончают зарубежная картина, чьё имя записано иероглифами, ответ
    карты прокатных имён, догадка по сходству и ряд кэша, снятый до того, как признак
    завели. Засчитать по такой пустоте безымянную дорожку за русскую - значит отдать
    зрителю чужой звук при непустой очереди позади.
    """
    assert not proven_native(Origin(name="Брат", year=1997), "Брат")


def test_a_named_original_outweighs_the_proof() -> None:
    """Имя латиницей у картины есть - отечественной она не станет ни от какой отметки."""
    assert not proven_native(Origin(title="Cars", name="Тачки", native=True), "Тачки")


def test_the_proof_must_be_about_the_asked_picture() -> None:
    """Доказательство про другую картину - не доказательство: имена сверяются."""
    assert not proven_native(Origin(name="Сестра", native=True), "Брат")


def test_a_silent_reference_leaves_everything_as_it_was() -> None:
    """Справка молчит - признак молчит тоже, и показ идёт прежним путём."""
    assert not proven_native(Origin(), "Брат")
