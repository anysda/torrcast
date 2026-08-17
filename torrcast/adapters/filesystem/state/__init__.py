"""Конфиг и состояние просмотра: ``/etc/torrcast/config.json`` (обязателен только
адрес ТВ) и ``/var/lib/torrcast/state.json`` (запись атомарная: tmp + rename).
Обе точки переопределяются переменными окружения ``TORRCAST_STATE`` и
``TORRCAST_CONFIG`` — это нужно тестам и локальному запуску.
"""

from torrcast.adapters.filesystem.state.config_keys import config_keys
from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.adapters.filesystem.state.file_state_store import FileStateStore
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.save_config import save_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic as _write_atomic
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry

__all__ = [
    "Config",
    "Entry",
    "FileStateStore",
    "State",
    "config_keys",
    "config_path",
    "load_config",
    "save_config",
    "state_path",
]
