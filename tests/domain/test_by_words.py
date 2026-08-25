"""Зеркало :mod:`torrcast.domain.by_words`: какая группа отвечает многословному запросу."""

from torrcast.domain.by_words import _by_words
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _group(copies: int) -> list[Picture]:
    releases = [Release(raw_name="кино", title="кино") for _ in range(copies)]
    return [Picture(title="кино", year=2003, releases=releases)]


def test_the_group_that_holds_every_asked_word_answers() -> None:
    """Слова запроса обязаны найтись все: лишние в имени группы - не помеха."""
    groups = {"the-matrix-reloaded-2003": _group(1), "the-animatrix": _group(1)}

    assert _by_words("the-matrix-reloaded", groups) == "the-matrix-reloaded-2003"


def test_the_narrower_name_wins_when_both_hold_the_words() -> None:
    """Из двух подходящих берём ту, где лишних слов меньше: она и есть спрошенная."""
    groups = {"the-matrix": _group(1), "the-matrix-reloaded-part-two": _group(1)}

    assert _by_words("the-matrix", groups) == "the-matrix"


def test_the_heavier_group_wins_between_names_of_the_same_shape() -> None:
    """Имена равной длины разводит вес: живее та группа, где раздач больше."""
    groups = {"the-matrix-one": _group(1), "the-matrix-two": _group(9)}

    assert _by_words("the-matrix", groups) == "the-matrix-two"


def test_a_one_word_query_is_not_answered_by_words() -> None:
    """Одно слово совпадает со слишком многим, и путь по словам тут запрещён."""
    assert _by_words("matrix", {"the-matrix": _group(1)}) is None


def test_a_query_no_group_holds_gets_nothing() -> None:
    assert _by_words("the-fifth-element", {"the-matrix": _group(1)}) is None
