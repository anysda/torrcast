"""Метка фазы старта: в след - всегда, в файл - только когда файл назван."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.stopwatch.mark import mark
from torrcast.adapters.filesystem.stopwatch.read import read
from torrcast.domain.timeline_env import TIMELINE_ENV
from torrcast.ports.journal import Silent, install


class _Spy(Silent):
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


def test_the_named_file_gets_the_phase_with_its_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Названный файл собирает метки обоих процессов: по ним и считают старт."""
    line = tmp_path / "timeline.jsonl"
    monkeypatch.setenv(TIMELINE_ENV, str(line))
    install(Silent())

    mark("юнит", ключ="abc")
    mark("картинка")

    names = [entry["name"] for entry in read(line)]
    assert names == ["юнит", "картинка"]
    assert read(line)[0]["ключ"] == "abc"


def test_a_mark_carries_the_wall_clock_and_the_process_that_made_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Время стенное, а не монотонное: у двух процессов монотонные часы разные.

    Процесс в метке стоит затем, чтобы в общей ленте было видно, чья это фаза -
    команды или юнита показа: без него две ноги старта сливаются в одну.
    """
    line = tmp_path / "timeline.jsonl"
    monkeypatch.setenv(TIMELINE_ENV, str(line))
    install(Silent())

    mark("поиск")

    import os
    import time

    (entry,) = read(line)
    assert entry["pid"] == os.getpid()
    assert abs(float(entry["at"]) - time.time()) < 60.0


def test_a_file_that_cannot_be_written_does_not_break_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Секундомер не имеет права уронить старт: недоступный путь просто молчит."""
    monkeypatch.setenv(TIMELINE_ENV, str(tmp_path / "нет-такого-каталога" / "timeline.jsonl"))
    install(Silent())

    mark("поиск")
