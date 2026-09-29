"""Проверяет запись тела полок: целиком на диск, а легший диск показ не роняет."""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.domain.json_value import JsonValue
from web.write_shelves import write_shelves


def test_the_body_is_written_whole(tmp_path: Path) -> None:
    """Записанное тело читается назад тем же."""
    body: dict[str, JsonValue] = {"fresh": [{"key": "a"}], "popular": [], "built_at": None}
    path = tmp_path / "shelves.json"

    write_shelves(path, body)

    assert json.loads(path.read_text(encoding="utf-8")) == body


def test_a_disk_that_refuses_the_write_does_not_raise(tmp_path: Path) -> None:
    """Каталог на месте файла - запись не состоялась, но исключение не ушло в фон."""
    path = tmp_path / "shelves.json"
    path.mkdir()

    write_shelves(path, {"fresh": []})

    assert path.is_dir()
    assert list(path.iterdir()) == []
