"""Зеркало :mod:`torrcast.usecases.warm._vault_disk`: чем прогрев меряет диск."""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.usecases.warm._vault_disk import _dirs, _disk_free, _size, _title, _touched, _weigh
from torrcast.usecases.warm.settings import META


def test_only_ready_pieces_are_weighed_and_a_broken_root_weighs_nothing(tmp_path: Path) -> None:
    """Вес прогретого - это его куски: посторонний файл рядом в счёт не идёт."""
    (tmp_path / "показ").mkdir()
    (tmp_path / "показ" / "v0.ts").write_bytes(b"0123456789")
    (tmp_path / "показ" / "v0.rec").write_text("метка", encoding="utf-8")

    assert _weigh(tmp_path) == 10
    assert _weigh(tmp_path / "нет такого") == 0
    assert _dirs(tmp_path / "нет такого") == []


def test_the_title_of_an_evicted_show_comes_from_its_passport(tmp_path: Path) -> None:
    """Вытесняемый показ называется по паспорту; нет паспорта - имени нет, а не беда."""
    (tmp_path / META).write_text(json.dumps({"key": "k", "title": "Кино"}), encoding="utf-8")

    assert _title(tmp_path) == "Кино"
    assert _title(tmp_path / "нет такого") == ""


def test_an_unreadable_partition_reports_no_free_space_rather_than_raising() -> None:
    """Не прочли раздел - ноль свободного: отказ по месту честнее исключения."""
    assert _disk_free(Path("/нет/такого/раздела")) == 0


def test_an_unreadable_file_weighs_nothing_and_a_missing_passport_is_nameless(
    tmp_path: Path,
) -> None:
    """Ноль тут безопасен: кусок, пропавший между глобом и ``stat``, отдача переживает."""
    assert _size(tmp_path / "нет.ts") == 0
    assert _weigh(tmp_path / "нет") == 0
    assert _title(tmp_path / "нет") == ""
    assert _touched(tmp_path / "нет") == 0.0
