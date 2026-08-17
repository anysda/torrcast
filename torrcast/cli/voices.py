"""Отладочная ручка ``cast voices <запрос>``: какие озвучки есть у релиза для ТВ.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.voices_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.cli.args import Args
from torrcast.usecases.voices_command import _cmd_voices


def voices(args: Args, command: Callable[[Args], int] = _cmd_voices) -> int:
    """``cast voices <запрос>`` — меню дорожек выбранной раздачи; показ не начинается."""
    return command(args)
