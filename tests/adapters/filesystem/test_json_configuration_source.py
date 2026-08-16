"""Проверяет чтение настроек из подставленного файла."""

from pathlib import Path

from torrcast.adapters.filesystem.json_configuration_source import JsonConfigurationSource


def test_loads_known_settings(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_args, **_kwargs: '{"tv": "10.0.0.2", "hls_port": 9000, "extra": 1}',
    )

    settings = JsonConfigurationSource({"TORRCAST_CONFIG": "/fake/config.json"}).load()

    assert settings.tv == "10.0.0.2"
    assert settings.hls_port == 9000
