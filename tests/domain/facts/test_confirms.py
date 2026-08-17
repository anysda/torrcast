"""Проверяет сверку года статьи с годом, который назвала раздача."""

from tests.articles import CARS, MOANA, MOANA_2026
from torrcast.domain.facts.confirms import confirms


def test_the_year_in_the_text_is_what_confirms_the_picture() -> None:
    """Единственная защита от чужого фильма — год в первых фразах статьи."""
    assert confirms(MOANA, 2016)
    assert not confirms(MOANA, 2026), "мультфильм 2016 года не выдать за ремейк"
    assert not confirms(MOANA_2026, 2026), "года в тексте нет - значит, подтвердить нечем"
    assert not confirms(CARS, None), "год картины неизвестен - сверять не с чем"
