"""Здоровье ленты для ``cast doctor``: есть ли она, когда писали, сколько весит."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal.health import health


def test_an_absent_tape_is_answered_honestly_and_not_by_zeros_that_look_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ленты нет - так и сказано: ``cast doctor`` не имеет права звать пустоту здоровой."""
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path / "пусто"))

    assert health() == (False, 0.0, 0)


def test_the_weight_is_the_whole_directory_and_the_time_is_the_freshest_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Вес - сумма суток, время - самая свежая запись: вопрос «пишется ли след».

    Считай вес по одному файлу - и переполненный каталог выглядел бы налегке; бери время
    первого файла - и живая лента считалась бы заброшенной уже на вторые сутки.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    old = tmp_path / "trace-20260101.jsonl"
    new = tmp_path / "trace-20260102.jsonl"
    old.write_text("x" * 10, encoding="utf-8")
    new.write_text("y" * 20, encoding="utf-8")
    stale = time.time() - 86400
    os.utime(old, (stale, stale))

    found, newest, total = health()

    assert found is True
    assert total == 30
    assert newest == pytest.approx(new.stat().st_mtime)


def test_files_that_are_not_the_tape_are_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Рядом с лентой лежит состояние - его вес к здоровью следа отношения не имеет."""
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    (tmp_path / "state.json").write_text("z" * 100, encoding="utf-8")
    (tmp_path / "trace-20260101.jsonl").write_text("x" * 10, encoding="utf-8")

    assert health()[2] == 10
