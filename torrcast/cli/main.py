"""Точка входа ``cast``: разбирает argv и зовёт команду, которую он называет.
Её отдаёт наружу :mod:`torrcast.cli`, ставит на неё console-script ``cast``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from torrcast.cli.answered import answered
from torrcast.cli.args import Args
from torrcast.cli.configure import configure
from torrcast.cli.doctor import doctor
from torrcast.cli.log import log
from torrcast.cli.parse_args import parse_args
from torrcast.cli.play import play
from torrcast.cli.releases import releases
from torrcast.cli.status import status
from torrcast.cli.stop import stop
from torrcast.cli.voices import voices
from torrcast.cli.worker import worker
from torrcast.ports.module import module

#: Имя команды (:attr:`Args.command`) - в саму команду. Ключи покрывают все ответы
#: разбора аргументов, поэтому промаха тут не бывает.
_COMMANDS: Mapping[str, Callable[[Args], int]] = {
    "configure": configure,
    "stop": lambda _args: stop(),
    "status": lambda _args: status(),
    "doctor": lambda _args: doctor(),
    "log": log,
    "releases": releases,
    "voices": voices,
    "worker": worker,
    "play": play,
}


def main(
    argv: Sequence[str] | None = None,
    commands: Mapping[str, Callable[[Args], int]] = _COMMANDS,
) -> int:
    """Точка входа console-script ``cast``."""

    def run() -> int:
        args = parse_args(argv)
        # IUTF8 на stdin включаем на всё время команды и возвращаем режим как было:
        # без него ssh-сессия ломает кириллицу в вопросах.
        with module("torrcast.console").terminal():
            return commands[args.command](args)

    # Коды возврата и хвост следа - на общем ответе командной строки, а не тут.
    return answered(run)
