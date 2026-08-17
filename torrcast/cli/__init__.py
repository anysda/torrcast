"""Пакет команд ``cast``: по файлу на команду плюс разбор аргументов.

Наружу отдаёт :func:`~torrcast.cli.main.main` - на неё ставит console-script ``cast``.
Ниже собирается совместимый плоский namespace прежнего монолита: перенесённые части
разрешают глобальные имена в своём модуле, и до полного разреза их доводят отсюда.
"""

from typing import Any

from torrcast.cli.args import Args
from torrcast.cli.main import main
from torrcast.cli.parse_args import TV_MENU, parse_args
from torrcast.ports.module import module

__all__ = ["TV_MENU", "Args", "main", "parse_args"]

#: Части прежнего монолита в порядке старшинства: последняя переопределяет предыдущие.
_PART_NAMES = (
    "torrcast.commands",
    "torrcast.usecases.cache_reserve",
    "torrcast.usecases.torrents",
    "torrcast.usecases.watch",
    "torrcast.usecases.say_showing",
    "torrcast.usecases.episode_duration",
    "torrcast.usecases.worker_loop",
    "torrcast.usecases.worker",
    "torrcast.usecases.releases_command",
    "torrcast.usecases.voices_command",
    "torrcast.usecases.log_command",
    "torrcast.usecases.doctor_command",
    "torrcast.play_command",
    "torrcast.discovery",
    "torrcast.reinforce",
    "torrcast.selection",
    "torrcast.selection_bench",
    "torrcast.playback",
    "torrcast.playback_revival",
    "torrcast.choice",
    "torrcast.ranking",
)
_PARTS = tuple(module(name) for name in _PART_NAMES)

# Функции в перенесённых частях разрешают глобальные имена в своём модуле.
# Доводим до каждой части полный namespace после завершения цепочки импортов.
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value) for name, value in vars(_part).items() if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)

__all__ = [name for name in globals() if not name.startswith("_")]
