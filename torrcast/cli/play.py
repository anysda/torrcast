"""Команда показа ``cast <запрос>``: счастливый путь от запроса до картинки на ТВ.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.cast_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.cli.args import Args
from torrcast.usecases.cast_command import _cmd_play


def play(args: Args, command: Callable[[Args], int] = _cmd_play) -> int:
    """``cast <запрос> [sNeM]`` — поиск, выбор картины и озвучки, запуск показа."""
    return command(args)
