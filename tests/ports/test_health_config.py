"""Проверяет форму порта настроек самопроверки."""

from torrcast.domain.settings import Settings
from torrcast.ports.health_config import HealthConfig


def test_health_config_is_a_port() -> None:
    """Порт остаётся протоколом без своей реализации."""
    assert HealthConfig.__name__ == "HealthConfig"


def test_settings_fit_the_port_as_they_are() -> None:
    """Доменные настройки подходят под порт без переходников."""
    config: HealthConfig = Settings(tv="10.0.0.50")
    assert config.tv == "10.0.0.50"
    assert config.receiver == "chromecast"
    assert config.transport == "http"
