"""Состояние просмотра в файле: чтение переживает любой мусор, запись атомарна."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.state import State
from torrcast.domain.entry import Entry


@pytest.fixture(autouse=True)
def _own_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "state.json"
    monkeypatch.setenv("TORRCAST_STATE", str(path))
    return path


def test_what_was_saved_is_what_is_loaded_back(_own_file: Path) -> None:
    """Запись и чтение сходятся: иначе «продолжить с того же места» теряет место."""
    State({"фильм": Entry("Моана", "magnet:?xt=1", pos=1272.4)}).save()

    assert State.load().entries["фильм"].pos == 1272.4


def test_a_missing_file_is_an_empty_state_and_not_a_crash(_own_file: Path) -> None:
    """Первый запуск идёт без файла состояния - это обычный случай, а не беда."""
    assert State.load().entries == {}


def test_a_broken_file_is_an_empty_state_too(_own_file: Path) -> None:
    """Битое состояние стоит одного забытого места в фильме, а не отказа показа.

    Здесь, в отличие от настроек, тихий откат правильный: состояние - это память об
    удобстве, и ронять из-за неё показ было бы дороже, чем начать фильм сначала.
    """
    _own_file.write_text("{не json", encoding="utf-8")
    assert State.load().entries == {}

    _own_file.write_text("[1, 2]", encoding="utf-8")
    assert State.load().entries == {}


def test_a_record_that_is_not_an_object_is_skipped_and_the_rest_survives(
    _own_file: Path,
) -> None:
    """Одна испорченная запись не уносит с собой всю память о просмотренном."""
    _own_file.write_text(
        '{"хорошая": {"title": "Моана", "magnet": "magnet:?xt=1", "pos": 10.0}, "плохая": 5}',
        encoding="utf-8",
    )

    entries = State.load().entries

    assert list(entries) == ["хорошая"]
    assert entries["хорошая"].pos == 10.0
