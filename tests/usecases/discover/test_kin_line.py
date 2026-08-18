"""Зеркало подсказки о живых соседях по франшизе: строка есть - но она только подсказка."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, pictures, row
from torrcast.usecases.discover.kin_line import KIN_SHOWN, _kin, kin_line

_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p", "a"),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p", "b"),
    row("Тачки 3 / Cars 3 (2017) BDRip 1080p", "c"),
    row("Тачки 4 / Cars 4 (2022) BDRip 1080p", "d"),
]


def test_the_parts_that_did_not_reach_the_menu_are_the_kin() -> None:
    """Соседи - это части франшизы с живыми раздачами, до меню не доехавшие."""
    whole = pictures(_CARS)
    lead = franchise("тачки", _CARS)[0]

    kin = _kin(lead, whole, {lead.key})

    assert [p.title for p in kin] == ["Тачки 2", "Тачки 3", "Тачки 4"]


def test_the_picture_itself_and_the_shown_ones_are_not_the_kin() -> None:
    """Себя и уже показанных в подсказку не берут: человек их и так видит."""
    whole = pictures(_CARS)
    lead = franchise("тачки", _CARS)[0]
    shown = {p.key for p in whole if p.title in {"Тачки", "Тачки 2", "Тачки 3"}}

    assert [p.title for p in _kin(lead, whole, shown)] == ["Тачки 4"]


def test_the_line_names_no_more_than_it_fits_and_offers_the_first() -> None:
    """Больше :data:`KIN_SHOWN` в строку не помещается, а ход предлагается по первому."""
    whole = pictures(_CARS)
    lead = franchise("тачки", _CARS)[0]

    line = kin_line(_kin(lead, whole, {lead.key}))

    assert line.count("(") == KIN_SHOWN
    assert line.startswith("в каталоге есть Тачки 2 (2011)")
    assert line.endswith("- cast тачки 2")


def test_without_kin_the_line_is_silence() -> None:
    """Соседей нет - и говорить не о чем: пустая строка, а не пустое обещание."""
    assert kin_line([]) == ""


def test_no_leader_means_no_kin_at_all() -> None:
    """Вожака не нашлось - соседей считать не от чего."""
    assert _kin(None, pictures(_CARS), set()) == []
