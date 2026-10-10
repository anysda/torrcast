"""Зеркало смены сетки по концу картинки: раскладка не портит запись, расхождение меряется точно.

Сами смены (прогрев новый или прежний) видны в зеркале конца картинки
(:mod:`tests.usecases.playback.test__ending`): здесь - то, что на нём не видно.
"""

from __future__ import annotations

from concurrent.futures import Future
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.usecases.playback.test__ending import CONTAINER, PICTURE, _ending, _Feed, _Recoder
from tests.usecases.playback.world import grid
from torrcast.usecases.playback._end_swap import _first_change, _layout, _swap


def test_the_first_change_is_where_the_tails_part() -> None:
    old, new = grid(CONTAINER), grid(PICTURE)

    cut = _first_change(old, new)

    assert old.end(cut - 1) == pytest.approx(new.end(cut - 1))
    assert old.end(cut) != pytest.approx(new.end(cut))
    assert _first_change(old, old) == old.count


def test_layout_leaves_the_entry_as_it_was() -> None:
    """Раскладка примеряет конец на время: запись меняет только сама смена сетки."""
    ending, world = _ending(Future(), _Feed(grid(CONTAINER)))

    lines, cut = _layout(ending, PICTURE)

    assert lines.count == grid(PICTURE).count and cut == _first_change(grid(CONTAINER), lines)
    assert world["watch"].entry.dur == CONTAINER


def test_layout_leaves_the_entry_even_when_the_layout_fails() -> None:
    ending, world = _ending(Future(), _Feed(grid(CONTAINER)))

    def broken() -> Any:
        raise RuntimeError("раскладка упала")

    ending.relayout = broken
    with pytest.raises(RuntimeError):
        _layout(ending, PICTURE)

    assert world["watch"].entry.dur == CONTAINER


def test_a_new_coder_resumes_where_the_show_already_is() -> None:
    """Поздняя смена: кодировщик тяжёлых кусков встаёт к месту показа, а не к его началу."""
    feed = _Feed(grid(CONTAINER), played=120.0)
    ending, world = _ending(Future(), feed)
    ending.warmer = cast(Any, SimpleNamespace(vault=SimpleNamespace(served=set()), rival=None))

    _swap(ending, PICTURE, grid(PICTURE), warm=False)

    new = cast(_Recoder, world["new"])
    assert new.played == 120.0 and new.events == ["stock", "start"]
    assert world["old"].events == ["stop"]
    assert cast(Any, ending.warmer).rival is new
