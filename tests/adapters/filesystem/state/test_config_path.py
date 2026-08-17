"""Путь настроек: общесистемный по умолчанию, переопределяемый окружением."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.config_path import DEFAULT_CONFIG_PATH, config_path


def test_the_default_home_is_the_system_directory_both_processes_can_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Настройки читает и юнит показа, поэтому лежат они там, где их видно обоим."""
    monkeypatch.delenv("TORRCAST_CONFIG", raising=False)

    assert config_path() == DEFAULT_CONFIG_PATH == Path("/etc/torrcast/config.json")


def test_the_environment_moves_the_whole_config_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Локальный запуск и тесты уводят настройки целиком, а не по одному ключу."""
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))

    assert config_path() == tmp_path / "config.json"


def test_an_empty_override_is_not_an_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая переменная - это её отсутствие, а не путь в корень файловой системы."""
    monkeypatch.setenv("TORRCAST_CONFIG", "")

    assert config_path() == DEFAULT_CONFIG_PATH
