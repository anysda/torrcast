"""Внутренняя команда ``cast --play-key KEY``: показ внутри transient-юнита.
Зовёт её :func:`torrcast.cli.main.main` из ``ExecStart`` юнита ``torrcast-play``,
сам сценарий живёт в :mod:`torrcast.usecases.worker`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.cli.args import Args
from torrcast.usecases.worker import _cmd_worker


def worker(args: Args, command: Callable[[str], int] = _cmd_worker) -> int:
    """``cast --play-key KEY`` — своя раздача, свой приёмник и своя уборка на выходе."""
    return command(str(args.play_key))
