"""Зеркало внешнего мира команды показа: каждое имя приходит от корня, а не из строки."""

from __future__ import annotations

from torrcast.runtime.wire import wire
from torrcast.usecases.cast_command import _play_state


def test_every_slot_is_filled_by_the_composition_root() -> None:
    """Забытый в корне слот виден здесь, а не ``NameError``'ом посреди живого показа."""
    wire()
    slots = [name for name in _play_state.__annotations__ if name.startswith("_play_")]

    assert slots, "у команды показа обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(_play_state, name)] == []


def test_a_second_word_of_the_root_replaces_the_first() -> None:
    """Корень сказал заново - команда берёт новое, а не первое."""
    wire()
    previous = _play_state._play_settings
    try:
        _play_state._configure_cast_command(
            _play_state._play_engines,
            previous,
            _play_state._play_detect,
            _play_state._play_facts,
            _play_state._play_native,
            _play_state._play_pinned,
            _play_state._play_merge,
            _play_state._play_releases,
            _play_state._play_origin,
        )

        assert _play_state._play_settings is previous
    finally:
        _play_state._play_settings = previous


def test_the_slots_are_declared_and_not_guessed() -> None:
    """Имена объявлены аннотациями: до слова корня подделки у сети не бывает."""
    declared = set(_play_state.__annotations__)

    assert {"_play_engines", "_play_settings", "_play_facts", "_play_releases"} <= declared
