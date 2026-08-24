"""Ответ командной строки: код возврата вместо трейсбека, чем бы команда ни кончилась.
Зовёт её точка входа (:func:`torrcast.cli.main.main`) вокруг самой команды.
"""

from __future__ import annotations

import contextlib
import io
import signal
import sys
from collections.abc import Callable

from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.stopped import _Stopped


class _Terminated(KeyboardInterrupt):
    """Команду остановил SIGTERM, а не штатный ``cast stop`` юнита показа."""


def _on_term(_number: int, _frame: object) -> None:
    raise _Terminated


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
    previous = signal.signal(signal.SIGTERM, _on_term)
    result = "необработанный отказ"
    code = EXIT_INFRA
    try:
        code = run()
        result = "успех" if code == EXIT_OK else "отказ"
        return code
    except NotFoundError as exc:
        code = EXIT_NOT_FOUND
        result = "не найдено"
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        code = EXIT_INFRA
        result = "отказ"
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except _Stopped:  # `cast stop` - штатный конец показа, а не отказ
        code = EXIT_OK
        result = "остановлен"
        return EXIT_OK
    except _Terminated:
        code = EXIT_INFRA
        result = "SIGTERM"
        print("команда прервана сигналом SIGTERM", file=sys.stderr)
        return EXIT_INFRA
    except KeyboardInterrupt:
        code = EXIT_INFRA
        result = "прерван с клавиатуры"
        print("команда прервана с клавиатуры", file=sys.stderr)
        return EXIT_INFRA
    except BrokenPipeError:  # `cast status | head` - не повод показывать трейсбек
        code = EXIT_OK
        result = "закрыт вывод"
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return EXIT_OK
    finally:
        signal.signal(signal.SIGTERM, previous)
        journal().emit("command", "finished", result=result, code=code)
        # Дожать хвост следа: фоновый писатель - демон, штатный выход обязан его дождаться.
        journal().shutdown()
