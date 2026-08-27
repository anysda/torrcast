"""Зеркало :mod:`torrcast.domain.ghost_keys_error`: приговор индексу везёт с собой карту."""

from __future__ import annotations

import pytest

from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.ghost_keys_error import GhostKeysError
from torrcast.domain.infra_error import InfraError

DRAWN = KeyMap(60.0, (Point(0.0, 0, 1), Point(2.0, 4096, 1)), 4096, 3, "mkv", 1)


def test_the_verdict_carries_the_index_it_condemned() -> None:
    """Разобранный индекс уезжает вместе с приговором: резать по нему нечем, взвешивать есть.

    Замер по живому файлу («Матрица» 1999, 18.2 ГБ, врущий индекс): 17 Range-проб из 17
    попали в настоящий кластер Matroska, метка каждого сошлась с картой в пределах кадра.
    Потеряй приговор эту карту - ровная сетка осталась бы без профиля тяжести.
    """
    with pytest.raises(GhostKeysError) as beda:
        raise GhostKeysError("индекс Cues врёт: точка 4131.693", DRAWN)

    assert beda.value.drawn is DRAWN
    assert str(beda.value) == "индекс Cues врёт: точка 4131.693"


def test_the_verdict_is_still_an_infrastructure_error_for_everyone_who_only_catches_that() -> None:
    """Ловят его прежним именем: показ знает про :class:`InfraError`, а не про этот класс.

    Мера отрицательная по смыслу: перестань он быть :class:`InfraError` - и врущий индекс
    полетел бы наружу трейсбеком мимо всех, кто ловит беду разбора.
    """
    with pytest.raises(InfraError):
        raise GhostKeysError("индекс Cues врёт", DRAWN)
