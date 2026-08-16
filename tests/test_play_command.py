"""Проверяет совместимый фасад команды показа."""

import torrcast.play_command


def test_play_command_facade_is_importable() -> None:
    assert torrcast.play_command._cmd_play is not None
