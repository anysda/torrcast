"""Команда ``cast log [--since]``: выжимка недельного диагностического следа.
Зовёт её :func:`torrcast.cli.main.main`, сам сценарий живёт в
:mod:`torrcast.usecases.log_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.args import Args
from torrcast.usecases.log_command import _cmd_log


def log(args: Args, command: Callable[[Args], int] = _cmd_log) -> int:
    """``cast log [--since]`` — последние сеансы ленты; ``--since`` двигает границу."""
    return command(args)
