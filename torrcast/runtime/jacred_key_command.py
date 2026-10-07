"""Собирает сохранение ключа JacRed для команды ``cast --jacred-key``."""

from __future__ import annotations

from torrcast.adapters.console.print_console import PrintConsole
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.domain.catalogs.phrase import phrase


def jacred_key_command(key: str) -> int:
    """Атомарно сохранить ключ в конфиге с остальными пользовательскими секретами."""
    config = load_config()
    config.jacred_key = key
    save_config(config)
    PrintConsole().write(phrase("runtime.jacred_key_saved"))
    return 0
