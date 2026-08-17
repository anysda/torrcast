"""Зеркало фейка команды без аргументов."""

from tests.fakes.command import FakeCommand


def test_a_call_is_counted_and_the_prepared_code_is_returned() -> None:
    command = FakeCommand(result=2)

    assert command() == 2
    assert command() == 2
    assert command.calls == 2


def test_a_fresh_command_is_a_success_that_nobody_called_yet() -> None:
    assert FakeCommand().calls == 0
    assert FakeCommand()() == 0
