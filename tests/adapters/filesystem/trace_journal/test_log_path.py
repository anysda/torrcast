"""Имя файла ленты: одни сутки - один файл, и даты сортируются как строки."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal.log_path import _PREFIX, _SUFFIX, log_path

#: Две метки времени внутри одних суток и одна - в следующих (UTC, полдень и вечер).
NOON = 1_754_654_400.0
EVENING = NOON + 8 * 3600
NEXT_DAY = NOON + 24 * 3600


def test_the_tape_is_cut_by_days_so_a_week_can_be_kept_and_dropped_by_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ротация идёт по суткам: один файл - одни сутки.

    Именно поэтому старое убирается удалением файла, а не переписыванием ленты: сложи все
    записи в один файл - и «держим неделю» превратилось бы в вычитание строк из растущего
    файла на каждом запуске показа.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))

    assert log_path(NOON) == log_path(EVENING)
    assert log_path(NOON) != log_path(NEXT_DAY)
    assert log_path(NOON).parent == tmp_path


def test_the_day_is_written_so_that_sorting_by_name_sorts_by_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """День - ``ГГГГММДД`` между приставкой и хвостом: только так строки идут по времени.

    На этом стоит и ротация (самые новые в хвосте отсортированного списка), и чтение
    недели подряд. Смени порядок частей даты - и «самый старый файл» перестало бы быть
    первой строкой сортировки, а сносила бы ротация что попало.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    names = [log_path(when).name for when in (NOON, NEXT_DAY)]

    assert _PREFIX == "trace-" and _SUFFIX == ".jsonl", "по этому имени ленту ищут все"
    assert names == sorted(names)
    assert names[0].startswith(_PREFIX) and names[0].endswith(_SUFFIX)
    assert names[0][len(_PREFIX) : -len(_SUFFIX)].isdigit()
    assert len(names[0][len(_PREFIX) : -len(_SUFFIX)]) == 8
