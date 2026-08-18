"""Зеркало :mod:`torrcast.domain.digest._warm_line`: вытеснение, кусок мимо сетки, прогресс."""

from __future__ import annotations

from tests.domain.digest.rows import rec
from torrcast.domain.digest._warm_line import _warm_line

STAMP = "+   0.0с "


def test_an_event_of_another_phase_is_not_this_readers_business() -> None:
    """``None`` тут значит «не моё событие»."""
    assert _warm_line(rec("buffering"), STAMP) is None


def test_the_eviction_says_whom_it_threw_out_and_how_much_that_freed() -> None:
    """Уборка ради места - решение, и по нему судят, хватает ли бюджета диска."""
    told = _warm_line(
        rec("evict", phase="warm", title="Тачки 3", freed=8_000_000_000, need=3_000_000_000), STAMP
    )

    assert told is not None
    assert "вытеснил «Тачки 3»: освободилось 8.0 ГБ под 3.0 ГБ" in told


def test_an_evicted_entry_without_a_title_is_named_by_its_key() -> None:
    """Имени нет - зовём ключом: безымянная строка не сказала бы ничего."""
    told = _warm_line(rec("evict", phase="warm", key="a1b2", freed=1e9, need=1e9), STAMP)

    assert told is not None and "«a1b2»" in told


def test_a_skew_tells_a_hole_apart_from_a_repacked_piece() -> None:
    """Кусок лёг мимо сетки - это либо дыра в прогретом, либо переложенный кусок."""
    hole = _warm_line(rec("skew", phase="warm", slot=7, off=-1.71, want=84.0, hole=True), STAMP)
    fixed = _warm_line(rec("skew", phase="warm", slot=7, off=-1.71, want=84.0, hole=False), STAMP)

    assert (
        hole is not None and "начало -1.71 с от границы 1:24 - место осталось непрогретым" in hole
    )
    assert fixed is not None and "кусок переложен заново" in fixed


def test_a_stalled_warmup_names_the_reason_and_a_running_one_does_not() -> None:
    """Прогрев встал - причина обязана быть в строке; идёт себе - причины и нет."""
    stalled = _warm_line(
        rec("stall", phase="warm", secs=600, dur=7200, share=0.083, size=1e9, why="бюджет диска"),
        STAMP,
    )
    running = _warm_line(
        rec("ready", phase="warm", secs=600, dur=7200, share=0.083, size=1e9), STAMP
    )

    assert stalled is not None and "прогрев встал: бюджет диска" in stalled
    assert running is not None and "прогрето 10:00 из 2:00:00 (8 %, 1.0 ГБ)" in running
    assert "встал" not in running
