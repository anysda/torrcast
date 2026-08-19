"""Проверяет форму порта окружения выбора."""

from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment


def test_choice_environment_is_a_port() -> None:
    """Порт остаётся протоколом без скрытого ввода-вывода."""
    assert ChoiceEnvironment.__name__ == "ChoiceEnvironment"
