"""Зеркально проверяет сценарий команды показа."""

from torrcast.usecases.cast_command import _cmd_play


def test_cast_command_scenario_is_importable() -> None:
    assert _cmd_play is not None
