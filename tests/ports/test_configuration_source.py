"""Проверяет контракт источника настроек и поведение его фейка."""

from dataclasses import FrozenInstanceError

import pytest

from tests.fakes.configuration_source import FakeConfigurationSource
from torrcast.domain.settings import Settings
from torrcast.ports.configuration_source import ConfigurationSource


def test_fake_returns_immutable_settings_and_records_load() -> None:
    settings = Settings(tv="Living room")
    fake = FakeConfigurationSource(settings)
    port: ConfigurationSource = fake
    assert port.load() is settings
    assert fake.load_count == 1
    with pytest.raises(FrozenInstanceError):
        settings.tv = "other"  # type: ignore[misc]
