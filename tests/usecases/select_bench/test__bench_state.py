"""Зеркало внешнего мира стенда: каждый слот приезжает от корня, а не из строки с именем."""

from __future__ import annotations

import torrcast.usecases.select_bench._bench_state as _bench_state
from torrcast.runtime.wire import wire


def test_the_composition_root_hands_the_bench_its_whole_outside_world() -> None:
    """Забытый в :func:`torrcast.runtime.wire.wire` слот виден здесь, а не на живом показе.

    Список берётся у самого модуля, поэтому новый слот забыть в этой проверке нельзя.
    """
    wire()
    slots = [name for name in _bench_state.__annotations__ if name.startswith("_bench_")]

    assert slots, "у стенда обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_bench_state, name)] == []


def test_the_contact_wait_arrives_as_a_factory_not_as_a_value() -> None:
    """Часы отсрочки у каждого прогрева свои - слот отдаёт завод, а не одно значение."""
    wire()

    first = _bench_state._bench_contact_wait(6.0)
    second = _bench_state._bench_contact_wait(6.0)

    assert first is not second
