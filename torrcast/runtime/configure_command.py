"""Собирает команду ``cast --tv``: поиск приёмников, конфиг и сценарий настройки.
Зовёт её :func:`torrcast.commands.main`.
"""

from __future__ import annotations

from torrcast.adapters.chromecast.network_receiver_finder import NetworkReceiverFinder
from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.config_file_store import ConfigFileStore
from torrcast.ports.module import module
from torrcast.usecases.configure import Configure


def configure_command(address: str | None = None) -> int:
    """``cast --tv [ip]`` — единственная настройка: адрес телевизора.

    ``None`` вместо адреса - это ``cast --tv`` без адреса: приёмники ищутся сами.
    """
    legacy = module("torrcast.commands")
    store = ConfigFileStore(legacy.load_config, legacy.save_config)
    return Configure(store, NetworkReceiverFinder(), PrintConsole()).run(address)
