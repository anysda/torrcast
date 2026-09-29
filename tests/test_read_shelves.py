"""Проверяет чтение тела полок: битый файл даёт пустые полки, чужое правило - экран."""

from __future__ import annotations

import json
from pathlib import Path

from web.built_by_rule import FIELD, RULE
from web.read_shelves import read_shelves

_EMPTY = {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}


def test_no_file_reads_as_empty_shelves(tmp_path: Path) -> None:
    """До первой сборки полки честно пусты, а не выдуманы."""
    assert read_shelves(tmp_path / "shelves.json") == _EMPTY


def test_a_broken_file_reads_as_empty_shelves(tmp_path: Path) -> None:
    """Недописанный файл не роняет показ."""
    path = tmp_path / "shelves.json"
    path.write_text('{"fresh": [', encoding="utf-8")

    assert read_shelves(path) == _EMPTY


def test_a_file_that_is_not_a_body_reads_as_empty_shelves(tmp_path: Path) -> None:
    """Список вместо тела - не тело полок."""
    path = tmp_path / "shelves.json"
    path.write_text("[]", encoding="utf-8")

    assert read_shelves(path) == _EMPTY


def test_a_body_of_another_rule_is_read_as_it_is(tmp_path: Path) -> None:
    """Тело чужого правила остаётся экраном, пока новое не собрано."""
    body = {FIELD: RULE - 1, "fresh": [{"key": "old"}], "popular": [], "built_at": None}
    path = tmp_path / "shelves.json"
    path.write_text(json.dumps(body), encoding="utf-8")

    assert read_shelves(path) == body
