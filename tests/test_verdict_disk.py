"""Вердикт играбельности на диске: переживает рестарт, чужое правило - как пустая запись."""

from __future__ import annotations

from pathlib import Path

import pytest

import web.verdict_disk as verdict_disk
from web.verdict_disk import VerdictDisk


def _disk(tmp_path: Path) -> VerdictDisk:
    return VerdictDisk(path=lambda: tmp_path / "shelf_verdicts.json")


def test_a_kept_verdict_is_read_back_by_a_restarted_process(tmp_path: Path) -> None:
    """Свежий предмет, указанный на тот же файл - это и есть рестарт службы."""
    _disk(tmp_path).keep("movie:tt1", 2, False)

    restarted = _disk(tmp_path)

    assert restarted.get("movie:tt1", 2) is False


def test_a_verdict_from_another_rule_reads_back_empty(tmp_path: Path) -> None:
    """Запись прежнего правила отбора не выдаётся за ответ нынешнего - RULE бывает бампнут."""
    _disk(tmp_path).keep("movie:tt1", 1, True)

    assert _disk(tmp_path).get("movie:tt1", 2) is None


def test_an_unknown_key_reads_back_empty(tmp_path: Path) -> None:
    """Ключ, которого на диске никогда не было - честное «не знаю», не отказ."""
    assert _disk(tmp_path).get("movie:absent", 2) is None


def test_a_broken_file_is_a_miss_not_a_failure(tmp_path: Path) -> None:
    (tmp_path / "shelf_verdicts.json").write_text("не json", encoding="utf-8")

    assert _disk(tmp_path).get("movie:tt1", 2) is None


def test_the_file_keeps_only_the_newest_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(verdict_disk, "ENTRIES", 2)
    disk = _disk(tmp_path)
    disk.keep("a", 2, True)
    disk.keep("b", 2, True)
    disk.keep("c", 2, True)

    reread = _disk(tmp_path)
    assert reread.get("a", 2) is None
    assert reread.get("b", 2) is True
    assert reread.get("c", 2) is True


__all__: list[str] = []
