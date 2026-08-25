"""Зеркало договора среды показа: слот берётся по имени, а не по порядку."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

import torrcast.usecases.playback._show_state as _state
from torrcast.usecases.playback.show_environment import ShowEnvironment


def test_the_environment_cannot_be_assembled_by_order() -> None:
    """Отрицательная проба: собрать среду по порядку нельзя вовсе.

    Два десятка доводов подряд перепутать местами - дело одной строки, и тайпчек ловит
    такую перестановку только там, где роды слотов разошлись. Названный слот закрывает
    и остальные случаи: подать значение молча не туда тут нечем.
    """
    assemble: Callable[..., object] = ShowEnvironment
    filled = [getattr(_state, name) for name in _state.__annotations__]

    with pytest.raises(TypeError, match="positional"):
        assemble(*filled)


def test_the_contract_names_every_slot_the_show_declares() -> None:
    """Договор и слоты показа считаются друг по другу, а не каждый сам по себе.

    Заведённый слот, которого нет в договоре, остался бы пустым на боевом пути и упал
    бы в момент показа: корню его класть неоткуда.
    """
    named = {field.name for field in dataclasses.fields(ShowEnvironment)}

    assert len(named) == len(_state.__annotations__)
