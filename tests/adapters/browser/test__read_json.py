"""Проверяет разбор JSON, которым читают оба письма вкладки."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.browser._read_json import _read_json


def test_a_missing_file_is_none_not_an_exception(tmp_path: Path) -> None:
    assert _read_json(tmp_path / "нет-файла.json") is None


def test_a_broken_file_is_none_not_an_exception(tmp_path: Path) -> None:
    target = tmp_path / "box.json"
    target.write_text("{не json", encoding="utf-8")

    assert _read_json(target) is None


def test_a_json_value_that_is_not_an_object_is_none(tmp_path: Path) -> None:
    target = tmp_path / "box.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")

    assert _read_json(target) is None


def test_a_well_formed_object_comes_back_as_written(tmp_path: Path) -> None:
    target = tmp_path / "box.json"
    target.write_text('{"a": 1}', encoding="utf-8")

    assert _read_json(target) == {"a": 1}
