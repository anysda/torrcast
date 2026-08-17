"""Чтение ленты меток: время выстраивает чтение, потому что пишут её два процесса."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.stopwatch.read import read


def test_an_unreadable_file_is_no_marks_and_not_a_crash(tmp_path: Path) -> None:
    """Ленты нет - значит меток нет; падать разбору не на чем."""
    assert read(tmp_path / "нет.jsonl") == []


def test_the_marks_of_two_processes_come_back_in_time_order(tmp_path: Path) -> None:
    """Порядок строк в файле не гарантирован никем: пишут его команда и юнит вперемешку.

    Считать по такой ленте старт можно только выстроив её по времени, и делает это
    чтение, а не запись: запись обязана быть одной атомарной строкой и ничем больше.
    """
    line = tmp_path / "timeline.jsonl"
    line.write_text(
        '{"at": 20.0, "name": "картинка"}\n{"at": 10.0, "name": "поиск"}\n',
        encoding="utf-8",
    )

    assert [entry["name"] for entry in read(line)] == ["поиск", "картинка"]


def test_a_torn_line_drops_only_itself(tmp_path: Path) -> None:
    """Хвост ленты рвётся законно: процесс гасят на любой фазе, и это не потеря замера."""
    line = tmp_path / "timeline.jsonl"
    line.write_text('{"at": 1.0, "name": "поиск"}\n{"at": 2.0, "na', encoding="utf-8")

    assert [entry["name"] for entry in read(line)] == ["поиск"]
