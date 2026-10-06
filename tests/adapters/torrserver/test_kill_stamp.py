"""Отметка последнего KILL службы раздач: общая для процессов, битая - как не было."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

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
    (tmp_path / "file").write_text("", encoding="utf-8")
    stamp = KillStamp(tmp_path / "file" / NAME)

    stamp.mark(1.0)
    assert stamp.at() is None


def test_a_reader_beside_a_mark_being_written_sees_the_old_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = tmp_path / NAME
    KillStamp(where).mark(1.0)
    seen: list[float | None] = []
    opened = io.open

    def slow_open(file: object, mode: str = "r", *args: object, **kwargs: object) -> object:
        handle = opened(file, mode, *args, **kwargs)  # type: ignore[call-overload]
        if "w" in mode:  # файл уже обрезан, новое ещё не записано: смотрит соседний процесс
            seen.append(KillStamp(where).at())
        return handle

    monkeypatch.setattr(io, "open", slow_open)
    KillStamp(where).mark(2.0)

    assert seen == [1.0], "в середине записи отметка старая, а не пустая"
    assert KillStamp(where).at() == 2.0
