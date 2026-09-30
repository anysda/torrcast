"""Первые записи «Продолжить» греются до клика, каждая своей рукой, уступая показу."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from torrcast.domain.continue_row import WARM_ROW
from web.record_warm import STEP, RecordWarm
from web.warm_job import WarmJob


def _job(magnet: str, at: float = 600.0) -> WarmJob:
    return WarmJob(magnet, f"http://торрент/{magnet}", at, f"{magnet}.mkv")


class _Hand:
    """Подставные прогрев, показ, часы и поток; прогрев отвечает сразу."""

    def __init__(self) -> None:
        self.warmed: list[tuple[str, bool]] = []
        self.show = False
        self.now = 0.0
        self.spawned: list[Callable[[], None]] = []
        self.during: Callable[[], None] = lambda: None
        self.warm = RecordWarm(
            warm=self._warm,
            showing=lambda: self.show,
            clock=lambda: self.now,
            wait=self._wait,
            spawn=self.spawned.append,
        )

    def _warm(self, source: str, *, at: float, alive: Any, name: str, done: Any) -> None:
        self.during()
        self.warmed.append((name, alive()))
        done.set()
        assert len(self.warmed) < 10, f"рука крутит прогрев вхолостую: {self.warmed[:3]}"

    def _wait(self, seconds: float) -> None:
        self.now += seconds
        self.show = False

    def run(self) -> None:
        while self.spawned:
            self.spawned.pop(0)()


def test_each_first_record_of_the_row_gets_its_own_hand() -> None:
    """По одной третья запись ждала двух соседок по 10-28 с и не успевала к клику."""
    hand = _Hand()
    hand.warm.name(["a", "b", "c"])
    hand.warm.offer(_job("b"))
    hand.warm.offer(_job("a"))

    assert len(hand.spawned) == 2, "каждая запись ряда греется сама, не в очереди"
    hand.run()

    assert sorted(hand.warmed) == [("a.mkv", True), ("b.mkv", True)]


def test_a_record_being_warmed_gets_no_second_hand() -> None:
    hand = _Hand()
    hand.warm.name(["a"])
    hand.warm.offer(_job("a"))
    hand.warm.offer(_job("a", at=900.0))  # закладка сдвинулась, пока рука ещё не дошла

    assert len(hand.spawned) == 1, "две руки читали бы одну раздачу дважды"
    hand.run()
    assert hand.warmed == [("a.mkv", True)]


def test_only_the_first_records_of_the_row_are_warmed() -> None:
    hand = _Hand()
    names = [str(n) for n in range(WARM_ROW + 1)]
    hand.warm.name(names)
    hand.warm.offer(_job(names[-1]))

    hand.run()

    assert hand.warmed == [], "за первыми записями - только метаданные держателя"


def test_a_warmed_record_is_not_warmed_again_until_the_bookmark_moves() -> None:
    hand = _Hand()
    hand.warm.name(["a"])
    hand.warm.offer(_job("a"))
    hand.run()

    hand.warm.offer(_job("a"))  # держатель будит запись каждые несколько секунд
    hand.run()
    assert hand.warmed == [("a.mkv", True)], "повторное открытие главной не множит прогрев"

    hand.warm.offer(_job("a", at=900.0))
    hand.run()
    assert len(hand.warmed) == 2


def test_a_record_from_the_start_is_not_warmed() -> None:
    hand = _Hand()
    hand.warm.name(["a"])
    hand.warm.offer(_job("a", at=0.0))

    assert hand.spawned == []


def test_warming_waits_for_a_live_show_to_end() -> None:
    hand = _Hand()
    hand.show = True
    hand.warm.name(["a"])
    hand.warm.offer(_job("a"))

    hand.run()

    assert hand.now == STEP, "показ шёл - прогрев ждал, а не читал рой"
    assert hand.warmed == [("a.mkv", True)]


def test_a_show_that_starts_midway_stops_the_warming() -> None:
    hand = _Hand()
    hand.warm.name(["a"])
    hand.warm.offer(_job("a"))

    def start_show() -> None:
        hand.during = lambda: None
        hand.show, hand.now = True, hand.now + STEP

    hand.during = start_show
    hand.run()

    assert hand.warmed == [("a.mkv", False), ("a.mkv", True)], "брошенная догревается после"


def test_a_record_the_page_pushed_out_of_the_row_stops_warming() -> None:
    hand = _Hand()
    hand.warm.name(["b"])
    hand.warm.offer(_job("b"))

    def row_moved() -> None:
        hand.during = lambda: None
        hand.warm.name(["x", "y", "z"])

    hand.during = row_moved
    hand.run()

    assert hand.warmed == [("b.mkv", False)], "за первыми записями - только метаданные"


def test_a_released_record_is_dropped_from_the_queue() -> None:
    hand = _Hand()
    hand.warm.name(["a"])
    hand.warm.offer(_job("a"))
    hand.warm.forget("a")

    hand.run()

    assert hand.warmed == []


def test_the_hand_runs_in_its_own_thread() -> None:
    finished = threading.Event()

    def warm(source: str, *, at: float, alive: Any, name: str, done: Any) -> None:
        done.set()
        finished.set()

    warm_hand = RecordWarm(warm=warm, showing=lambda: False)
    warm_hand.name(["a"])
    warm_hand.offer(_job("a"))

    assert finished.wait(3)
