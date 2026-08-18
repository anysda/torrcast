"""Зеркало внешнего мира отбора: каждый слот приезжает от корня, а не из строки с именем."""

from __future__ import annotations

import torrcast.usecases.select._pick_state as _pick_state
from torrcast.runtime.wire import wire


def test_the_composition_root_hands_the_selection_its_whole_outside_world() -> None:
    """Забытый в :func:`torrcast.runtime.wire.wire` слот виден здесь, а не на живом показе.

    Список берётся у самого модуля, поэтому новый слот забыть в этой проверке нельзя.
    """
    wire()
    slots = [name for name in _pick_state.__annotations__ if name.startswith("_select_")]

    assert slots, "у отбора обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_pick_state, name)] == []


def test_the_engines_of_the_selection_are_a_working_factory() -> None:
    """Слот службы раздач - не имя, а завод: по адресу он отдаёт готовую службу."""
    wire()

    engines = _pick_state._select_engines("http://127.0.0.1:8090")

    assert hasattr(engines, "add") and hasattr(engines, "stream_url")
