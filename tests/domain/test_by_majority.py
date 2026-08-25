"""Зеркало :mod:`torrcast.domain.by_majority`: какое из имён считаем настоящим."""

from collections import Counter

from torrcast.domain.by_majority import by_majority


def test_the_name_written_by_most_releases_wins() -> None:
    assert by_majority(Counter({"брат": 2, "брат-по-крови": 5})) == "брат-по-крови"


def test_a_tie_is_broken_by_the_shorter_name() -> None:
    """Поровну - берём короткое: длинное обычно дописано пометками одной раздачи."""
    assert by_majority(Counter({"брат-по-крови": 3, "брат": 3})) == "брат"


def test_names_of_the_same_length_are_taken_in_a_settled_order() -> None:
    """Порядок словаря не смеет решать за нас: два прогона отвечают одинаково."""
    assert by_majority(Counter({"яма": 1, "дом": 1})) == "дом"
