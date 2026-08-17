"""Проверяет вычёркивание источника, чей вклад в отданный паспорт не попал."""

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.facts.without_source import without_source


def test_a_source_whose_contribution_was_dropped_leaves_the_mark() -> None:
    """🔴 TC-450. Отметка описывает ОТДАННЫЙ ответ, а не путь, которым его собирали."""
    both = Origin(title="The Hobbit", source="wiki+map")
    assert without_source(both, SOURCE_MAP).source == "wiki"


def test_the_last_remaining_source_is_never_crossed_out() -> None:
    """Ответ откуда-то всё же взялся - иначе счёт потерял бы его вовсе."""
    only_map = Origin(title="Brat 2", source=SOURCE_MAP)
    assert without_source(only_map, SOURCE_MAP) == only_map
