"""Зеркало :mod:`torrcast.runtime.configure_cli`: слоты слоя команд заполнены корнем.

Проверка поимённая нарочно. Промах тут молчаливый: слот остаётся пустым до первой
команды, и `cast status` падает не на стенде, а у человека.
"""

from __future__ import annotations

from tests.conftest import module_of
from torrcast.adapters.console.console.terminal import terminal
from torrcast.runtime.configure_cli import configure_cli
from torrcast.runtime.configure_command import configure_command
from torrcast.runtime.status_command import status_command
from torrcast.runtime.stop_command import stop_command

#: Модули команд, а не одноимённые единицы из пакета: `torrcast.cli.main` - это функция.
main_module = module_of("torrcast.cli.main")
status_module = module_of("torrcast.cli.status")
stop_module = module_of("torrcast.cli.stop")
configure_module = module_of("torrcast.cli.configure")


def test_every_slot_of_the_command_layer_is_filled_by_the_root() -> None:
    """Каждый слот держит ту единицу, которую ему назначил корень, а не тёзку."""
    configure_cli()

    assert main_module._TERMINAL is terminal
    assert status_module._SESSION is status_command
    assert stop_module._SESSION is stop_command
    assert configure_module._SETTINGS is configure_command
