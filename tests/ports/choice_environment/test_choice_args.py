"""Аргументы команды: договор их возит и читать не разрешает."""

from torrcast.cli.args import Args
from torrcast.ports.choice_environment import ChoiceArgs


def test_the_real_command_arguments_fit_the_carrier() -> None:
    """Имя пустое нарочно: аргументы разбирает команда, окружение выбора их только возит."""
    carried: ChoiceArgs = Args(query=["моана"])

    assert isinstance(carried, Args)
