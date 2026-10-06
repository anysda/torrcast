"""Перемотки моста: номер и цель для вкладки и нажатия подряд от защёлки (TC-1169)."""

from __future__ import annotations

from hass.aim import LANDED_SECONDS, Aim
from torrcast.domain.playback_snapshot import PlaybackSnapshot


class _Clock:
    """Часы теста: время идёт ровно туда, куда его двигают."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _shown(position: float, key: str = "movie:муха", paused: str = "") -> PlaybackSnapshot:
    return PlaybackSnapshot(
        key=key, title="Муха", position=position, duration=3600.0, moved=True, paused=paused
    )


def _place(aim: Aim, shown: PlaybackSnapshot) -> float:
    """Позиция снимка, каким его увидит карточка."""
    answered = aim.seen(shown)
    assert answered is not None
    return answered.position


def test_each_seek_of_the_bridge_gets_a_new_number_and_its_target() -> None:
    """TC-1169: вкладка на ТВ узнаёт о перемотке моста по новому номеру в снимке.

    Номер живёт и после приземления: опрос вкладки мог пропустить саму защёлку.
    """
    clock = _Clock()
    aim = Aim(clock=clock)
    assert aim.sought(_shown(1060.0)) is None

    _place(aim, _shown(1060.0))
    aim.at(-300.0)
    assert aim.sought(_shown(1060.0)) == {"n": 1, "to": 760.0}

    clock.now = LANDED_SECONDS + 1.0
    _place(aim, _shown(745.1))
    assert aim.sought(_shown(745.1)) == {"n": 1, "to": 760.0}

    aim.at(600.0)
    assert aim.sought(_shown(745.1)) == {"n": 2, "to": 1345.1}


def test_a_seek_of_another_show_is_not_named() -> None:
    aim = Aim(clock=_Clock())
    _place(aim, _shown(60.0))
    aim.at(30.0)

    assert aim.sought(_shown(60.0, key="movie:другое")) is None
    assert aim.sought(None) is None


def test_presses_in_a_row_add_up_from_the_latched_place() -> None:
    """TC-1169: нажатие поверх неприземлившейся перемотки считается от её цели."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(1000.0))
    aim.at(60.0)
    clock.now = 0.5
    aim.at(60.0)
    clock.now = 1.0
    aim.at(-30.0)

    assert _place(aim, _shown(1000.0)) == 1091.0
    assert aim.sought(_shown(1000.0)) == {"n": 3, "to": 1091.0}


def test_after_the_window_a_press_counts_from_the_truth_again() -> None:
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(1000.0))
    aim.at(60.0)
    clock.now = LANDED_SECONDS
    _place(aim, _shown(1000.0))
    aim.at(60.0)

    assert aim.sought(_shown(1000.0)) == {"n": 2, "to": 1060.0}


def test_the_latch_clock_does_not_run_past_the_end_of_the_film() -> None:
    """Стенд 06-10-2026: «+600» у конца встал на 10143.9 из 10143.9, а часы защёлки
    повели карточку дальше - 10144.8, 10145.7 при длительности 10143.9."""
    clock = _Clock()
    aim = Aim(clock=clock)

    _place(aim, _shown(3598.0))
    aim.at(600.0)
    clock.now = 4.0

    assert _place(aim, _shown(3598.0)) == 3600.0, "часы защёлки ушли за конец фильма"
