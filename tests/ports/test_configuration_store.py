"""Порт настроек задаёт контракт чтения и сохранения."""

from torrcast.ports.configuration_store import ConfigurationStore


def test_configuration_store_is_protocol() -> None:
    assert ConfigurationStore.__name__ == "ConfigurationStore"
