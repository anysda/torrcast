"""Зеркало команды показа: полнота её внешнего мира."""

from __future__ import annotations

from torrcast.runtime.wire import wire
from torrcast.usecases.cast_command import _play_state
from torrcast.usecases.cast_command._cmd_play import _cmd_play


def test_the_composition_root_hands_the_command_its_whole_outside_world() -> None:
    """Каждое имя внешнего мира команда получает от корня - или падает на живом показе.

    Слоты объявлены аннотациями и до слова корня пусты: забытый в
    :func:`torrcast.runtime.wire.wire` слот виден здесь, а не ``NameError``'ом посреди
    показа, когда первые куски уже уехали на приёмник. Список берётся у самого модуля,
    поэтому новый слот забыть в этой проверке нельзя.
    """
    wire()
    slots = [name for name in _play_state.__annotations__ if name.startswith("_play_")]
    assert slots, "у команды показа обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_play_state, name)] == []
    assert _cmd_play is not None
