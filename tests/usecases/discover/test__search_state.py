"""Зеркало внешнего мира поиска: каждый слот приезжает от корня, а не берётся из строки."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from tests.usecases.discover.world import row
from torrcast.runtime.wire import wire


def test_the_composition_root_hands_the_search_its_whole_outside_world() -> None:
    """Забытый в :func:`torrcast.runtime.wire.wire` слот виден здесь, а не ``NameError``'ом.

    Список берётся у самого модуля, поэтому новый слот забыть в этой проверке нельзя.
    """
    wire()
    slots = [name for name in _search_state.__annotations__ if name.startswith("_search_")]

    assert slots, "у поиска обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_search_state, name)] == []


def test_the_catalogue_of_the_search_parses_the_raw_rows_it_is_given() -> None:
    """Слот каталога - не имя, а работающий разбор: он и склеивает, и разбирает выдачу."""
    wire()
    rows = [row("Тачки / Cars (2006) BDRip 1080p", "a")]

    merged = _search_state._search_catalogue.merge(rows, [])

    assert len(merged) == 1
    assert [r.title for r in _search_state._search_catalogue.to_releases(merged)] == ["Тачки"]
