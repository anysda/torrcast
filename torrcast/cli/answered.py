"""Ответ командной строки: код возврата вместо трейсбека, чем бы команда ни кончилась.
Зовёт её точка входа (:func:`torrcast.cli.main.main`) вокруг самой команды.
"""

from __future__ import annotations

import contextlib
import io
import sys
from collections.abc import Callable

from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.stopped import _Stopped


def answered(run: Callable[[], int]) -> int:
    """Выполнить команду и перевести её отказ в код возврата.

    🔴 SIGTERM от ``cast stop`` поднимает исключение - иначе показ не прошёл бы через
    ``finally`` и не записал позицию, - но исход у него штатный: выйди мы кодом 2, и
    systemd пометил бы юнит ``failed`` после каждой нормальной остановки. Ctrl-C на
    вопросе при этом отказом быть не перестаёт, и разводит их тип исключения.

    Команда приходит аргументом, а не именем: так её подменяет и проверка, и точка
    входа - той же дорогой, какой её отдаёт разбор аргументов боевого запуска.
    """
    # Прогресс идёт вперемешку с ошибками в stderr: без построчного сброса врёт порядок.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        return run()
    except NotFoundError as exc:
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        journal().emit("error", "error", text=str(exc)[:200])
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
        journal().shutdown()
