"""Путь состояния: общесистемный по умолчанию, переопределяемый окружением."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.state_path import DEFAULT_STATE_PATH, state_path


def test_the_default_home_is_the_service_directory_and_not_a_home_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Состояние пишут два процесса, и дом у файла обязан быть общий.

    Уедь он в домашний каталог - юнит показа под своей учётной записью писал бы своё
    состояние, а команда читала бы чужое, и «продолжить с того же места» перестало бы
    работать ровно у того, ради кого его и заводили.
    """
    monkeypatch.delenv("TORRCAST_STATE", raising=False)

    assert state_path() == DEFAULT_STATE_PATH == Path("/var/lib/torrcast/state.json")


def test_the_environment_moves_the_whole_state_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Переопределение нужно тестам и локальному запуску - и уводит файл целиком."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))

    assert state_path() == tmp_path / "state.json"


def test_an_empty_override_is_not_an_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая переменная - это её отсутствие, а не путь в корень файловой системы."""
    monkeypatch.setenv("TORRCAST_STATE", "")

    assert state_path() == DEFAULT_STATE_PATH
