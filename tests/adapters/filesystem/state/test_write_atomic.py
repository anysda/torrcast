"""Атомарная запись JSON: читатель видит либо старый файл, либо новый, но не половину."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.torrcast_error import TorrcastError


def test_the_target_is_replaced_whole_and_never_shown_half_written(tmp_path: Path) -> None:
    """Замена идёт переименованием: временный файл лежит рядом, а не поверх цели.

    Пиши мы прямо в цель - читатель (второй процесс показа) успевал бы прочесть
    оборванный JSON и получить пустое состояние вместо своего.
    """
    target = tmp_path / "state.json"
    target.write_text('{"старое": 1}', encoding="utf-8")

    _write_atomic(target, {"новое": 2})

    assert json.loads(target.read_text("utf-8")) == {"новое": 2}
    assert [path.name for path in tmp_path.iterdir()] == ["state.json"]


def test_the_directory_is_made_on_the_way(tmp_path: Path) -> None:
    """Первая запись идёт туда, где каталога ещё нет вовсе."""
    target = tmp_path / "ещё-нет" / "state.json"

    _write_atomic(target, {"ключ": "значение"})

    assert target.exists()


def test_the_text_is_readable_by_a_human_and_stable_between_runs(tmp_path: Path) -> None:
    """Ключи отсортированы, отступы есть, кириллица не экранирована.

    Файл смотрят глазами и правят руками; прыгающий порядок ключей делал бы каждую
    запись похожей на изменение, которого не было.
    """
    target = tmp_path / "state.json"

    _write_atomic(target, {"бета": 2, "альфа": 1})

    text = target.read_text("utf-8")
    assert text.index('"альфа"') < text.index('"бета"')
    assert "\\u" not in text
    assert text.endswith("\n")


def test_a_failed_write_names_the_file_and_leaves_no_temporary_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Отказ диска - понятная ошибка с путём, а не голый OSError из недр записи."""
    target = tmp_path / "state.json"

    def refuse(_self: Path, _other: Path) -> None:
        raise OSError("места нет")

    monkeypatch.setattr(Path, "replace", refuse)

    with pytest.raises(TorrcastError, match="could not write"):
        _write_atomic(target, {"ключ": 1})

    assert list(tmp_path.iterdir()) == []
