"""Чтение ленты: файлов суток много, а лента одна и читается по возрастанию времени."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal.log_path import log_path
from torrcast.adapters.filesystem.trace_journal.records import records

NOON = 1_754_654_400.0
EVENING = NOON + 8 * 3600
NEXT_DAY = NOON + 24 * 3600


def test_the_week_is_read_back_as_one_tape_in_time_order_across_its_day_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Файлов суток много, а лента одна: читается она вся и по возрастанию времени.

    Делить по суткам - решение хранения, а не смысла: человек спрашивает «что было», и
    сеанс, начавшийся до полуночи и кончившийся после, обязан читаться подряд. Порядок
    внутри файла при этом не гарантирован никем - пишет ленту фоновый писатель, - поэтому
    время выстраивает само чтение, а не запись.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    log_path(NOON).write_text(
        f'{{"at": {EVENING}, "event": "вечер"}}\n{{"at": {NOON}, "event": "полдень"}}\n',
        "utf-8",
    )
    log_path(NEXT_DAY).write_text(f'{{"at": {NEXT_DAY}, "event": "назавтра"}}\n', "utf-8")

    assert [rec["event"] for rec in records()] == ["полдень", "вечер", "назавтра"]


def test_asking_the_tape_from_a_moment_keeps_that_moment_and_drops_only_the_past(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``since`` отрезает ПРОШЛОЕ, а названный миг остаётся: граница включающая.

    Спрашивают ленту так ровно затем, чтобы увидеть свой сеанс, а не весь недельный след, и
    метка начала сеанса - это метка его первой записи. Отрежь границу строго - и человек
    терял бы ту самую строку, от которой считал; переверни сравнение - и получал бы вместо
    своего сеанса всё, что было до него.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    log_path(NOON).write_text(
        f'{{"at": {NOON}, "event": "полдень"}}\n{{"at": {EVENING}, "event": "вечер"}}\n',
        "utf-8",
    )

    assert [rec["event"] for rec in records(since=EVENING)] == ["вечер"]
    assert [rec["event"] for rec in records(since=NOON)] == ["полдень", "вечер"]


def test_a_torn_line_means_that_line_is_missing_and_nothing_more(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Оборванный хвост ленты законен: писатель - демон, и последняя запись рвётся.

    Битая строка не имеет права ни уронить ``cast log``, ни задвоить соседнюю: разбор и
    проверка стоят под одним подавлением именно потому, что врозь неразобранная строка
    оставляла в переменной ПРЕДЫДУЩУЮ запись, и та уходила в выдачу вторым разом.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    log_path(NOON).write_text(
        f'{{"at": {NOON}, "event": "полдень"}}\n{{"at": {EVENING}, "ev',
        "utf-8",
    )

    assert [rec["event"] for rec in records()] == ["полдень"]


def test_a_missing_directory_is_an_empty_tape_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Следа ещё не было - это пустая лента: спрашивать её можно до первого показа."""
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path / "нет-такого"))

    assert records() == []
