"""Запись настроек на диск - атомарная, потому что читают их и на ходу.

Зовут её первичная настройка и команды, меняющие адрес приёмника."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic

if TYPE_CHECKING:
    from torrcast.domain.config import Config


def save_config(config: Config) -> None:
    """Записать конфиг атомарно, создав каталог при необходимости."""
    _write_atomic(config_path(), asdict(config))
