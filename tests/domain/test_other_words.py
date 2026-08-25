"""Зеркало :mod:`torrcast.domain.other_words`: что печатать, когда нашлось не спрошенное."""

from torrcast.domain.other_words import other_words
from torrcast.domain.picture import Picture


def test_a_picture_named_by_the_query_needs_no_word() -> None:
    """Нашлось спрошенное - подмены не было, и говорить не о чем."""
    assert other_words("Брат", Picture(title="Брат", year=1997)) == ""


def test_the_original_name_answers_for_the_query_too() -> None:
    assert other_words("Brother", Picture(title="Брат", year=1997, original="Brother")) == ""


def test_a_picture_of_another_name_is_named_aloud() -> None:
    """Молчаливая подмена запрещена: взяли другое - печатаем, что именно."""
    assert other_words("Кровь", Picture(title="Брат", year=1997)) == "Брат"


def test_nothing_found_is_not_a_substitution() -> None:
    assert other_words("Брат", None) == ""
