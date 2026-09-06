"""Путь кэша полок: общесистемный по умолчанию, переопределяемый окружением."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.shelves_cache_path import (
    DEFAULT_SHELVES_CACHE_PATH,
    shelves_cache_path,
)


def test_the_default_home_is_the_service_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кэш пишет фон полок, а читает веб-маршрут - дом у файла общий, как у состояния."""
    monkeypatch.delenv("TORRCAST_SHELVES_CACHE", raising=False)

    assert shelves_cache_path() == DEFAULT_SHELVES_CACHE_PATH
    assert Path("/var/lib/torrcast/shelves.json") == DEFAULT_SHELVES_CACHE_PATH


def test_the_environment_moves_the_whole_cache_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Переопределение нужно тестам и локальному запуску - и уводит файл целиком."""
    monkeypatch.setenv("TORRCAST_SHELVES_CACHE", str(tmp_path / "shelves.json"))

    assert shelves_cache_path() == tmp_path / "shelves.json"


def test_an_empty_override_is_not_an_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая переменная - это её отсутствие, а не путь в корень файловой системы."""
    monkeypatch.setenv("TORRCAST_SHELVES_CACHE", "")

    assert shelves_cache_path() == DEFAULT_SHELVES_CACHE_PATH
