"""Точка входа ``cast``: разбирает argv, зовёт команду и переводит отказы в коды возврата.
Её отдаёт наружу :mod:`torrcast.cli`, ставит на неё console-script ``cast``.
"""

from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Callable, Mapping, Sequence

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
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.module import module
from torrcast.usecases.stopped import _Stopped

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
    # Прогресс идёт вперемешку с ошибками в stderr: без построчного сброса врёт порядок.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    # Терминал и лента следа - внешний мир, и слой команд зовёт их по имени, а не импортом.
    trace = module("torrcast.trace")
    try:
        args = parse_args(argv)
        # IUTF8 на stdin включаем на всё время команды и возвращаем режим как было:
        # без него ssh-сессия ломает кириллицу в вопросах.
        with module("torrcast.console").terminal():
            return commands[args.command](args)
    except NotFoundError as exc:
        trace.emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        trace.emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except _Stopped:  # `cast stop` - штатный конец показа, а не отказ
        return EXIT_OK
    except KeyboardInterrupt:
        return EXIT_INFRA
    except BrokenPipeError:  # `cast status | head` - не повод показывать трейсбек
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return EXIT_OK
    finally:
        # Дожать хвост следа: фоновый писатель - демон, штатный выход обязан его дождаться.
        trace.shutdown()
