"""Зеркало :mod:`torrcast.domain.one_name_is_enough`: хватило ли одного имени картины."""

from torrcast.domain.one_name_is_enough import _one_name_is_enough
from torrcast.domain.picture import Picture


def test_a_query_that_one_title_answers_by_itself() -> None:
    """Все слова запроса нашлись в одном названии - смешивать имена было незачем."""
    picture = Picture(title="Брат по крови", year=1997, original="Brother")

    assert _one_name_is_enough({"брат", "крови"}, picture)


def test_the_original_name_answers_by_itself_too() -> None:
    picture = Picture(title="Брат", year=1997, original="Brother of Mine")

    assert _one_name_is_enough({"brother", "mine"}, picture)


def test_a_query_split_across_the_two_names_needs_both() -> None:
    picture = Picture(title="Брат", year=1997, original="Brother")

    assert not _one_name_is_enough({"брат", "brother"}, picture)
