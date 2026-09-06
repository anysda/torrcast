"""Проверяет атомарную запись, которой пользуются оба файла-письма вкладке."""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.adapters.browser._write_json import _write_json


def test_the_payload_lands_whole_and_readable(tmp_path: Path) -> None:
    target = tmp_path / "box.json"

    _write_json(target, {"a": 1, "b": "x"})

    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": "x"}


def test_a_missing_directory_is_made_rather_than_refused(tmp_path: Path) -> None:
    target = tmp_path / "нет-каталога" / "box.json"

    _write_json(target, {"a": 1})

    assert target.exists()


def test_no_stray_temp_file_survives_a_successful_write(tmp_path: Path) -> None:
    target = tmp_path / "box.json"

    _write_json(target, {"a": 1})

    assert list(tmp_path.iterdir()) == [target]
