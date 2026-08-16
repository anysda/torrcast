"""Проверяет форму порта уточнения."""

from torrcast.ports.reinforce_environment import ReinforceEnvironment


def test_reinforce_environment_is_protocol() -> None:
    assert ReinforceEnvironment.__name__ == "ReinforceEnvironment"
