"""Пакет команд ``cast``: по файлу на команду плюс разбор аргументов.

Наружу отдаёт :func:`~torrcast.cli.main.main` - на неё ставит console-script ``cast``.
"""

from torrcast.cli.args import Args
from torrcast.cli.main import main
from torrcast.cli.parse_args import TV_MENU, parse_args

__all__ = ["TV_MENU", "Args", "main", "parse_args"]
