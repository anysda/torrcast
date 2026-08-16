"""Проверки версии публичного пакета."""

from torrcast.domain.version import __version__


def test_version_is_semantic() -> None:
    assert __version__.count(".") == 2
