"""Зеркало отказа от подъёма: без отказа проходит молча, с отказом гасит и прекращает."""

from __future__ import annotations

import re
from typing import cast

import pytest

from tests.usecases.playback.world import FakeProgress, FakeShow
from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.ports.abandon import slot as abandon_slot
from torrcast.ports.progress.progress import Progress
from torrcast.ports.show_unit.show_unit import ShowUnit
from torrcast.usecases.playback.refuse_called_off import refuse_called_off


def test_a_raise_nobody_called_off_goes_on_at_both_turns() -> None:
    """Без отказа оба поворота пропускают подъём дальше и юнита не трогают."""
    unit = FakeShow()

    refuse_called_off()
    refuse_called_off(cast(Progress, FakeProgress()), cast(ShowUnit, unit))

    assert unit.stopped == 0, "подъём погасили, хотя от него никто не отказывался"


def test_the_turn_before_the_unit_ends_the_raise_without_touching_a_unit() -> None:
    """Отказ до юнита прекращает подъём отменой: гасить ещё нечего, и незачем."""
    abandon_slot.install(lambda: True)

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        refuse_called_off()


def test_the_turn_over_a_live_unit_puts_the_show_out_itself() -> None:
    """Отказ при живом юните гасит показ сам: снаружи его гасить может быть уже некому."""
    unit = FakeShow()
    abandon_slot.install(lambda: True)

    with pytest.raises(CancelledError, match=re.escape(phrase("playback.abandoned"))):
        refuse_called_off(cast(Progress, FakeProgress()), cast(ShowUnit, unit))

    assert unit.stopped == 1, "показ, от которого отказались, остался жить"
