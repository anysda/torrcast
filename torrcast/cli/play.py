"""Команда показа ``cast <запрос>``: счастливый путь от запроса до картинки на ТВ.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.cast_command`.
"""

from __future__ import annotations

from collections.abc import Callable

import torrcast.usecases.cast_command._play_state as _state
from torrcast.domain.args import Args
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.torrents import _release_parked


def _after_start() -> None:
    """Уборка, которой клик не ждёт: раздачи закладок сносятся, когда показ уже поднят."""
    _release_parked(_state._play_settings())


def play(
    args: Args,
    command: Callable[[Args], int] = _cmd_play,
    after: Callable[[], None] = _after_start,
) -> int:
    """``cast <запрос> [sNeM]`` — поиск, выбор картины и озвучки, запуск показа.

    ``after`` идёт, когда команда кончилась: картинка на экране или отказ. Снос раздачи в
    TorrServer стирает её кэш и ждёт общий замок службы, и в пути клика стоил до 3.0 с.
    """
    try:
        return command(args)
    finally:
        after()
