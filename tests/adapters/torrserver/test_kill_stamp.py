"""Отметка последнего KILL службы раздач: общая для процессов, битая - как не было."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.torrserver.kill_stamp import NAME, KillStamp


def test_a_mark_is_seen_by_another_reader_of_the_same_state() -> None:
    KillStamp().mark(1700000000.25)

    assert KillStamp().at() == 1700000000.25


def test_no_mark_reads_as_never_killed() -> None:
    assert KillStamp().at() is None


def test_a_broken_mark_reads_as_never_killed(tmp_path: Path) -> None:
    (tmp_path / NAME).write_text("garbage", encoding="utf-8")

    assert KillStamp(tmp_path / NAME).at() is None


def test_an_unwritable_place_does_not_break_the_restart(tmp_path: Path) -> None:
    stamp = KillStamp(tmp_path / "missing" / NAME)

    stamp.mark(1.0)
    assert stamp.at() is None
