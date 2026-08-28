"""Щуп замера меряет правило отвода захода, а не свою копию его."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "seekgaps", Path(__file__).resolve().parent.parent / "scripts/seekgaps.py"
)
assert SPEC is not None and SPEC.loader is not None
gaps = importlib.util.module_from_spec(SPEC)
sys.modules["seekgaps"] = gaps
SPEC.loader.exec_module(gaps)


class _Silent(gaps.Pilot):  # type: ignore[misc, name-defined]
    """Измеритель, у которого ни одно место не читается: граница остаётся неизмеренной."""

    def __call__(self, url: str, at: float, timeout: float, keys: object = None) -> float:
        self.asks += 1
        raise gaps.UnreachableError("рой не ответил")


def _remembering(seen: dict[float, float]) -> Any:
    """Измеритель, которому все места уже известны: ffmpeg он не поднимает ни разу."""
    return gaps.Pilot("url", 1.0, seen=dict(seen))


def _printing(text: str) -> Any:
    """Подделка ffprobe, печатающая ровно то, что печатает настоящий на этом контейнере."""

    def _probe(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, text, "")

    return _probe


def test_the_probe_asks_every_nonzero_uniform_boundary() -> None:
    assert gaps.boundaries(35.001, 10.0) == [10.0, 20.0, 30.0]
    assert gaps.boundaries(34.999, 10.0) == [10.0, 20.0]


def test_a_start_landing_before_the_boundary_costs_one_run() -> None:
    pilot = _remembering({200.0: 196.0})

    got = gaps.outcome(pilot, 200.0, extra=2)

    assert got.kind == gaps.AT_ONCE
    assert got.asked == 1
    assert pilot.runs == 0


def test_a_start_landing_late_is_pulled_back_behind_the_boundary() -> None:
    pilot = _remembering({100.0: 112.0, 88.0: 95.0})

    got = gaps.outcome(pilot, 100.0, extra=2)

    assert got.kind == gaps.SETTLED
    assert (got.stood, got.settled) == (112.0, 95.0)
    assert got.asked == 2


def test_the_rule_gives_up_and_the_probe_prices_the_step_that_would_have_saved_it() -> None:
    # Отвод удваивается с уезда 15 с: 4985, 4970, 4940, 4880 - все они дают то же место.
    stuck = dict.fromkeys((5000.0, 4985.0, 4970.0, 4940.0, 4880.0), 5015.0)
    pilot = _remembering({**stuck, 4760.0: 4700.0})

    got = gaps.outcome(pilot, 5000.0, extra=2)

    assert got.kind == gaps.GAVE_UP
    assert got.settled == 5015.0
    # Пятый шаг отводит на 240 с и накрывает границу: цена поднятого потолка названа.
    assert got.rescued == 5
    assert got.asked == 6


def test_a_boundary_nobody_can_measure_is_not_counted_as_a_landing() -> None:
    got = gaps.outcome(_Silent("url", 1.0), 300.0, extra=2)

    assert got.kind == gaps.UNMEASURED
    assert got.stood is None
    assert got.error == "рой не ответил"


def test_the_widest_gap_is_between_distinct_reachable_landings() -> None:
    rows = [
        gaps.Outcome(10.0, 4.0, 4.0, 1, gaps.AT_ONCE),
        gaps.Outcome(20.0, 4.0, 4.0, 1, gaps.AT_ONCE),
        gaps.Outcome(30.0, 92.0, 92.0, 5, gaps.GAVE_UP),
    ]

    assert gaps.widest(rows) == (4.0, 92.0, 88.0)


def test_the_report_counts_every_verdict_and_both_prices() -> None:
    rows = [
        gaps.Outcome(10.0, 4.0, 4.0, 1, gaps.AT_ONCE),
        gaps.Outcome(20.0, 26.0, 18.0, 2, gaps.SETTLED),
        gaps.Outcome(30.0, 92.0, 92.0, 6, gaps.GAVE_UP, rescued=5),
        gaps.Outcome(40.0, None, None, 1, gaps.UNMEASURED, error="рой не ответил"),
    ]
    pilot = _remembering({})
    pilot.asks, pilot.runs = 10, 7

    report = gaps.summary(rows, pilot, 45.0, 10.0)

    assert (report["сразу"], report["отведён"], report["сдался"]) == (1, 1, 1)
    assert report[gaps.UNMEASURED] == 1
    assert report["границы сдачи"] == [30.0]
    assert report["спасли бы шагом"] == [5]
    # Посадки 4, 26 и 92: широчайший провал считается между СОСЕДНИМИ из них, а не с краю.
    assert report["самый широкий провал"] == 66.0
    assert report["шире 80 с"] is False
    assert (report["спрошено правилом"], report["прогонов ffmpeg"]) == (10, 7)


def test_a_container_offset_is_translated_into_the_film_timeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # У .m2ts видео начинается с тысяч секунд: без перевода посадка 4209.218 выглядела бы
    # уехавшей на весь сдвиг вперёд, и правило отвода мерилось бы на выдуманном провале.
    monkeypatch.setattr(gaps, "land", lambda _url, _at, _timeout: (4209.218, ""))
    pilot = gaps.Pilot("url", 1.0, begins=4199.167)

    stood = pilot("url", 10.0, 1.0)

    assert round(stood, 3) == 10.051
    assert pilot.runs == 1


def test_the_container_name_is_read_past_the_blank_line_mpegts_prints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # mpegts печатает четыре строки на тот же запрос, matroska - две. По номеру строки имя
    # контейнера у mpegts попало бы на пустую.
    monkeypatch.setattr(gaps.subprocess, "run", _printing("4200.000000\n\n4200.000000\nmpegts\n"))

    assert gaps.film_begins("url", 1.0) == 4200.0


def test_the_mp4_family_is_never_shifted(monkeypatch: pytest.MonkeyPatch) -> None:
    # TC-699: у mp4 карта, сетка и заход живут в метках контейнера, и вычитать нечего.
    monkeypatch.setattr(gaps.subprocess, "run", _printing('0.023000\n"mov,mp4,m4a"\n'))

    assert gaps.film_begins("url", 1.0) == 0.0
