"""Отладочная ручка ``cast releases <запрос>``: таблица релизов каждой картины.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.releases_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.args import Args
from torrcast.usecases.releases_command import _cmd_releases


def releases(args: Args, command: Callable[[Args], int] = _cmd_releases) -> int:
    """``cast releases <запрос>`` — что нашлось и в каком порядке; показ не начинается."""
    return command(args)
