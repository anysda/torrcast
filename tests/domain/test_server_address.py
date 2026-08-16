"""Tests for the started-server address value."""

from torrcast.domain.server_address import ServerAddress


def test_keeps_public_base_url() -> None:
    assert ServerAddress("http://host:8080").base_url == "http://host:8080"
