"""Зеркало :mod:`torrcast.domain.by_subtitle`: находим часть по её подзаголовку."""

from torrcast.domain.by_subtitle import _by_subtitle
from torrcast.domain.picture import Picture


def test_a_part_is_found_by_the_words_after_the_colon() -> None:
    """«Перезагрузка» - это запрос: имя франшизы человек в него не повторяет."""
    pictures = [Picture(title="Матрица: Перезагрузка", year=2003)]

    assert [p.title for p in _by_subtitle("Перезагрузка", pictures)] == ["Матрица: Перезагрузка"]


def test_the_subtitle_of_the_original_name_counts_too() -> None:
    """Подзаголовок бывает написан только латиницей: он тот же вход в картину."""
    pictures = [Picture(title="Матрица 2", year=2003, original="The Matrix: Reloaded")]

    assert [p.title for p in _by_subtitle("Reloaded", pictures)] == ["Матрица 2"]


def test_the_franchise_name_alone_is_not_a_subtitle() -> None:
    """Слово до двоеточия подзаголовком не является: иначе нашлась бы вся франшиза."""
    assert _by_subtitle("Матрица", [Picture(title="Матрица: Перезагрузка", year=2003)]) == []


def test_an_empty_query_is_not_a_subtitle() -> None:
    assert _by_subtitle(" ", [Picture(title="Матрица: Перезагрузка", year=2003)]) == []
