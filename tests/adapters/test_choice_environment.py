"""Проверяет системное окружение выбора."""

from torrcast.adapters.choice_environment import environment


def test_choice_environment_has_terminal_width() -> None:
    """Ширина терминала всегда положительна."""
    assert environment.columns() > 0
