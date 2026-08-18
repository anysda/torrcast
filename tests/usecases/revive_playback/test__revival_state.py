"""Зеркало полей лестницы подъёма: чем она меряет темноту и что о ней уже знает."""

from __future__ import annotations

import pytest

from tests.fakes.clock import FakeClock
from torrcast.domain.revive_settings import REVIVE_DROP, REVIVE_LIVED, REVIVE_PAUSE
from torrcast.usecases.revive_playback._revival_state import _RevivalState


def test_a_fresh_ladder_is_not_in_the_dark_and_has_spent_nothing() -> None:
    """Темноты нет, попыток нет, виноватого нет: лестница начинает с чистого листа."""
    state = _RevivalState(clock=FakeClock())

    assert (state.since, state.began, state.why, state.tries) == (0.0, 0.0, "", 0)
    assert (state.blamed, state.dropped, state.ended) == (False, False, False)


def test_the_pauses_come_from_the_receiver_profile_by_default() -> None:
    """Умолчания выдержек - осторожный профиль: мера молчания приёмника, а не наша."""
    state = _RevivalState(clock=FakeClock())

    assert (state.pause, state.drop, state.lived) == (REVIVE_PAUSE, REVIVE_DROP, REVIVE_LIVED)


def test_a_named_clock_wins_over_the_configured_one() -> None:
    """Сухому прогону нужны свои часы, и названные аргументом сильнее общих."""
    mine = FakeClock(now=7.0)

    assert _RevivalState(clock=mine).clock is mine


def test_the_ladder_holds_nothing_it_was_not_asked_to_hold() -> None:
    """Лишнего поля лестнице не приписать: её состояние объявлено целиком."""
    with pytest.raises(AttributeError):
        _RevivalState(clock=FakeClock()).invented = 1  # type: ignore[attr-defined]
