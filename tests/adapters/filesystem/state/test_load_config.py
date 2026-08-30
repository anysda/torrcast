"""Чтение настроек: нет файла - умолчания, битый файл - понятная ошибка."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError


def test_a_missing_file_is_defaults_and_not_a_refusal_to_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Первый запуск идёт без файла настроек, и это нормальный случай, а не авария."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "нет.json"))

    assert load_config() == Config()


def test_the_written_keys_come_back_as_they_were_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Написанное в файле побеждает умолчание - иначе настраивать было бы нечем."""
    path = tmp_path / "config.json"
    path.write_text('{"tv": "10.0.0.50"}', encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    assert load_config().tv == "10.0.0.50"


def test_a_broken_file_is_named_out_loud_instead_of_quietly_becoming_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Битый JSON - это ошибка с именем файла, а не тихий откат к умолчаниям.

    Тихий откат означал бы показ на чужой адрес: человек правил файл, ошибся в запятой,
    и получил бы поведение «как из коробки» без единого слова о причине.
    """
    path = tmp_path / "config.json"
    path.write_text("{не json", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    with pytest.raises(TorrcastError, match="broken config"):
        load_config()


def test_a_json_that_is_not_an_object_is_broken_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Список вместо объекта - тот же битый конфиг: разбирать по ключам его нечем."""
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_CONFIG", str(path))

    with pytest.raises(TorrcastError, match="expected a JSON object"):
        load_config()
