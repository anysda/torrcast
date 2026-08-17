"""Секундомер старта: метка идёт в след всегда, а в файл - только когда он назван."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.stopwatch import mark, read
from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.ports.journal import _Silent, install, journal


class _Spy(_Silent):
    """Молчащая лента, которая запоминает, что ей сказали."""

    def __init__(self) -> None:
        self.marks: list[str] = []

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.marks.append(f"{phase}/{event}")


def test_a_mark_reaches_the_journal_without_a_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без переменной окружения файла нет, а в ленте фаза есть: она даровая."""
    monkeypatch.delenv(TIMELINE_ENV, raising=False)
    spy = _Spy()
    install(spy)

    mark("поиск", раздач=3)

    assert spy.marks == ["timeline/поиск"]
    install(_Silent())


def test_the_named_file_gets_the_phase_with_its_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Названный файл собирает метки обоих процессов: по ним и считают старт."""
    line = tmp_path / "timeline.jsonl"
    monkeypatch.setenv(TIMELINE_ENV, str(line))
    install(_Silent())

    mark("юнит", ключ="abc")
    mark("картинка")

    names = [entry["name"] for entry in read(line)]
    assert names == ["юнит", "картинка"]
    assert read(line)[0]["ключ"] == "abc"


def test_an_unreadable_file_is_no_marks_and_not_a_crash(tmp_path: Path) -> None:
    """Ленты нет - значит меток нет; падать разбору не на чем."""
    assert read(tmp_path / "нет.jsonl") == []
    assert journal() is not None
