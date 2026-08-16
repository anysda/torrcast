"""Совместимая реализация CLI сохраняет прежнюю точку входа."""

from torrcast import commands_legacy


def test_legacy_cli_keeps_parser() -> None:
    assert commands_legacy.parse_args(["status"]).command == "status"
