"""Лента меток из файла как таблица: время от нуля и цена каждой фазы."""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.adapters.filesystem.stopwatch_report import stopwatch_report


def _lane(path: Path, *marks: dict[str, object]) -> Path:
    path.write_text("\n".join(json.dumps(mark) for mark in marks) + "\n", encoding="utf-8")
    return path


def test_the_table_counts_from_the_first_mark(tmp_path: Path) -> None:
    """Без выбранного нуля лента считается от первой метки."""
    lane = _lane(
        tmp_path / "лента.jsonl",
        {"at": 1000.0, "name": "старт", "pid": 7},
        {"at": 1002.5, "name": "ответы", "pid": 7},
    )

    printed = stopwatch_report(lane).splitlines()

    assert printed[0].split() == ["фаза", "от", "нуля", "цена", "pid"]
    assert printed[1].startswith("старт") and "+0.00" in printed[1]
    assert "+2.50" in printed[2] and "2.50" in printed[2] and printed[2].endswith("7")


def test_the_named_mark_becomes_the_zero(tmp_path: Path) -> None:
    """Старт меряется от ответа человека, поэтому ноль выбирается меткой, а не строкой."""
    lane = _lane(
        tmp_path / "лента.jsonl",
        {"at": 1000.0, "name": "старт", "pid": 7},
        {"at": 1002.0, "name": "ответы", "pid": 7},
        {"at": 1003.0, "name": "картинка", "pid": 8},
    )

    printed = stopwatch_report(lane, "ответы").splitlines()

    assert "-2.00" in printed[1], "то, что было до нуля, уходит в минус"
    assert "+0.00" in printed[2]
    assert "+1.00" in printed[3]


def test_marks_are_read_in_time_order_whoever_wrote_them(tmp_path: Path) -> None:
    """Ленту пишут два процесса, и по файлу они идут вперемешку."""
    lane = _lane(
        tmp_path / "лента.jsonl",
        {"at": 1002.0, "name": "показ", "pid": 8},
        {"at": 1000.0, "name": "старт", "pid": 7},
    )

    printed = stopwatch_report(lane).splitlines()

    assert printed[1].startswith("старт") and printed[2].startswith("показ")


def test_an_empty_or_missing_lane_says_so(tmp_path: Path) -> None:
    """Секундомер выключен - об этом и говорим, а не падаем на пустом файле."""
    assert stopwatch_report(tmp_path / "нет.jsonl") == "меток нет"
    assert stopwatch_report(_lane(tmp_path / "пусто.jsonl")) == "меток нет"
