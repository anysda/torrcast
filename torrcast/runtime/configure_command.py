"""Собирает команду ``cast --tv``: поиск приёмников, конфиг и сценарий настройки.
Зовёт её :func:`torrcast.cli.main.main`.
"""

from __future__ import annotations

from torrcast.adapters.chromecast.network_receiver_finder import NetworkReceiverFinder
from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.config_file_store import ConfigFileStore
from torrcast.adapters.filesystem.state import load_config, save_config
from torrcast.usecases.configure import Configure


def configure_command(address: str | None = None) -> int:
    """``cast --tv [ip]`` — единственная настройка: адрес телевизора.

    ``None`` вместо адреса - это ``cast --tv`` без адреса: приёмники ищутся сами.
    """
    store = ConfigFileStore(load_config, save_config)
    return Configure(store, NetworkReceiverFinder(), PrintConsole()).run(address)
