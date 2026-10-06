"""Показ и ползунок карточки встают в одно место: у нуля и у конца файла (TC-1169).

Нажатия идут тем же путём, что у моста: :func:`hass.say.say` кладёт слово в файл-пульт,
настоящий читатель показа его забирает, :func:`torrcast.usecases.choice._ctl._ctl`
исполняет. Карточку считает :class:`hass.aim.Aim` из тех же нажатий.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hass.aim import Aim
from hass.say import say
from tests.usecases.choice.test__ctl import Pult
from tests.usecases.choice.world import Outside, outside
from torrcast.adapters.choice_environment import _SystemChoiceEnvironment
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.position import Position
from torrcast.domain.seek_place import END_MARGIN
from torrcast.usecases.choice._ctl import _ctl
from web.tv_steer import tv_steer

_DURATION = 7200.0


class _At(Pult):
    """Пульт, стоящий на известном месте картины известной длины."""

    def __init__(self, pos: float) -> None:
        super().__init__()
        self.pos = pos

    def position(self, front: float = 0.0) -> Position:
        return Position(self.pos, _DURATION, playing=True, state="PLAYING")


def _show_lands(pos: float, presses: list[float], monkeypatch: pytest.MonkeyPatch) -> float:
    """Куда встал показ: нажатия моста подряд, потом один опрос читателя."""
    for by in presses:
        say(f"seekby {by:g}")
    receiver = _At(pos)
    with outside(Outside(command=_SystemChoiceEnvironment().read_command())):
        _ctl(receiver)
    [done] = receiver.done
    return float(done.removeprefix("seek "))


def _card_shows(pos: float, presses: list[float]) -> float:
    """Что рисует ползунок карточки сразу после тех же нажатий."""
    aim = Aim(clock=lambda: 0.0)
    shown = PlaybackSnapshot(key="movie:k", title="K", position=pos, duration=_DURATION)
    aim.seen(shown)
    for by in presses:
        aim.at(by)
    answered = aim.seen(shown)
    assert answered is not None
    return answered.position


@pytest.fixture(autouse=True)
def _ctl_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))


def test_back_past_the_start_then_forward_lands_the_show_where_the_card_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Позиция 100, «-240», «+60»: показ вставал на 0, карточка ~40 с рисовала 60."""
    show = _show_lands(100.0, [-240.0, 60.0], monkeypatch)
    card = _card_shows(100.0, [-240.0, 60.0])

    assert (show, card) == (60.0, 60.0)


def test_five_forwards_at_the_end_stop_inside_the_file_on_both_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пять «+600» у конца файла слали приёмнику место за длительностью."""
    near_end = _DURATION - 400.0
    show = _show_lands(near_end, [600.0] * 5, monkeypatch)
    card = _card_shows(near_end, [600.0] * 5)

    assert show == card == _DURATION - END_MARGIN


def test_the_tab_cast_remote_stops_inside_the_file_too() -> None:
    receiver = _At(_DURATION - 100.0)

    assert tv_steer(receiver, None, "seekby", 3000.0)

    assert receiver.done == [f"seek {_DURATION - END_MARGIN}"]


def test_seeks_of_one_sign_still_add_up_into_one_step() -> None:
    say("seekby 60")
    say("seekby 60")
    say("seekby -240")
    say("seekby 60")

    assert _SystemChoiceEnvironment().read_command() == "seekby 120 -240 60"
