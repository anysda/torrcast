"""Реэкспорт команды показа: закладка, меню, отбор релиза, строки перед стартом и запуск.

Ни строчки логики - каждая часть живёт в своём файле пакета. Прежние имена собраны
здесь потому, что плоский namespace прежнего монолита (:mod:`torrcast.cli`) спрашивает
их у одного модуля.
"""

from __future__ import annotations

from torrcast.usecases.cast_command._bookmark import (
    _account_watched,
    _continue_picked,
    _from_start,
)
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.cast_command._entry_for import _entry_for
from torrcast.usecases.cast_command._notes import _notes
from torrcast.usecases.cast_command._play_state import _configure_cast_command

__all__ = [
    "_account_watched",
    "_choose",
    "_cmd_play",
    "_configure_cast_command",
    "_continue_picked",
    "_entry_for",
    "_from_start",
    "_notes",
]
