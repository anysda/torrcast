"""Зеркало :mod:`torrcast.domain.with_subtitled`: к найденному добираются части по подзаголовку."""

from torrcast.domain.picture import Picture
from torrcast.domain.with_subtitled import _with_subtitled

MATRIX = Picture(title="Матрица", year=1999)
RELOADED = Picture(title="Матрица: Перезагрузка", year=2003)


def test_a_part_named_by_its_subtitle_joins_what_was_found() -> None:
    """Спросили «Перезагрузка» - показать одну «Матрицу» значило бы включить не то."""
    found = _with_subtitled([MATRIX], "Перезагрузка", [MATRIX, RELOADED], None)

    assert [p.title for p in found] == ["Матрица", "Матрица: Перезагрузка"]


def test_a_query_that_named_a_number_is_left_as_it_is() -> None:
    """Номер части человек назвал сам, и дополнять его выбор нечем."""
    found = _with_subtitled([MATRIX], "Перезагрузка", [MATRIX, RELOADED], 1)

    assert [p.title for p in found] == ["Матрица"]


def test_nothing_found_stays_nothing() -> None:
    """Пустой ответ добором не наполняется: это был бы отказ, подменённый догадкой."""
    assert _with_subtitled([], "Перезагрузка", [MATRIX, RELOADED], None) == []
