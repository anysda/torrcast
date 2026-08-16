"""Зеркально проверяет отладочную ручку списка озвучек."""

from torrcast.usecases.voices_command import _cmd_voices


def test_voices_command_is_importable() -> None:
    assert _cmd_voices is not None
