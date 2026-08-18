"""Зеркало слоя разбора командной строки."""

from torrcast.cli.parse_args import parse_args


def test_commands_keeps_parser_in_cli_layer() -> None:
    """Разбор аргументов остаётся в модуле CLI."""
    assert parse_args(["status"]).command == "status"
