"""Хранилище настроек меняет только своё и не стирает остальной конфиг."""

from dataclasses import dataclass
from typing import Any

from torrcast.adapters.filesystem.config_file_store import ConfigFileStore


@dataclass
class _Config:
    tv: str | None = None
    receiver: str = "chromecast"
    torrserver_url: str = "http://127.0.0.1:8090"
    hls_readrate: float = 1.0  # ключ показа, о котором сценарий настройки не знает


def test_settings_are_read_from_the_shared_keys() -> None:
    config = _Config(tv="10.0.0.50")
    store = ConfigFileStore(lambda: config, lambda _saved: None)

    settings = store.load()

    assert (settings.tv, settings.receiver) == ("10.0.0.50", "chromecast")


def test_saving_keeps_the_keys_the_scenario_never_saw() -> None:
    config = _Config(tv="10.0.0.50", hls_readrate=1.5)
    saved: list[Any] = []
    store = ConfigFileStore(lambda: config, saved.append)

    store.save(store.load().__class__(tv="mock", receiver="mock"))

    assert saved == [config]
    assert (config.tv, config.receiver) == ("mock", "mock")
    assert config.hls_readrate == 1.5, "чужие ключи конфига запись сценария не трогает"
