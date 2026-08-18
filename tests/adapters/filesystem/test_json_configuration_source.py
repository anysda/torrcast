"""Читает настройки из НАСТОЯЩЕГО файла: путь берётся из окружения, чужие ключи молчат."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.json_configuration_source import JsonConfigurationSource


def test_loads_known_settings(tmp_path: Path) -> None:
    """Известные ключи доезжают, неизвестный не роняет чтение.

    Конфиг пишут руками, и лишний ключ там - дело обычное: упади источник на нём, показ
    не поднялся бы вовсе из-за строки, которая ему не нужна.
    """
    config = tmp_path / "config.json"
    config.write_text('{"tv": "10.0.0.2", "hls_port": 9000, "extra": 1}', encoding="utf-8")

    settings = JsonConfigurationSource({"TORRCAST_CONFIG": str(config)}).load()

    assert settings.tv == "10.0.0.2"
    assert settings.hls_port == 9000


def test_a_missing_file_is_defaults_and_not_a_crash(tmp_path: Path) -> None:
    """Конфига ещё нет - это первый запуск, а не авария."""
    settings = JsonConfigurationSource({"TORRCAST_CONFIG": str(tmp_path / "нет.json")}).load()

    assert settings == type(settings)()
