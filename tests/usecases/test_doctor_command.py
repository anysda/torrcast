"""Зеркально проверяет команду самопроверки окружения."""

from torrcast.usecases.doctor_command import _cmd_doctor


def test_doctor_command_is_importable() -> None:
    assert _cmd_doctor is not None
