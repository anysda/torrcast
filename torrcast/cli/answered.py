"""Ответ командной строки: код возврата вместо трейсбека, чем бы команда ни кончилась.
Зовёт её точка входа (:func:`torrcast.cli.main.main`) вокруг самой команды.
"""

from __future__ import annotations

import contextlib
import io
import signal
import sys
from collections.abc import Callable

from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_CANCELLED, EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.start_refusal import RECEIVER_DID_NOT_ANSWER, SOURCE_DID_NOT_ANSWER
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.ports.refusal_record import refusal_record
from torrcast.usecases.stopped import _Stopped


class _Terminated(KeyboardInterrupt):
    """Команду остановил SIGTERM, а не штатный ``cast stop`` юнита показа."""


def _on_term(_number: int, _frame: object) -> None:
    raise _Terminated


def _refusal_of(exc: BaseException) -> str:
    """Договорное слово отказа подъёма по классу аварии; неразличимое - пусто.

    Слово уходит в порт записи (:func:`torrcast.ports.refusal_record.refusal_record`),
    потому что отказ, который ждёт страница, случается в ДРУГОМ процессе - юните
    показа. Пустая строка - честная граница, а не пропуск: причина, которую продукт
    различить не может, не выдумывается, и экран остаётся коротким
    (:mod:`torrcast.domain.start_refusal`).
    """
    if isinstance(exc, ServerDownError):
        return SOURCE_DID_NOT_ANSWER
    if isinstance(exc, StartRefusedError):
        # До сюда отказ загрузки доезжает, только миновав лестницу воскрешения:
        # приёмник показ не взял, и поднять его не вышло.
        return RECEIVER_DID_NOT_ANSWER
    return ""


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
    # 🔴 `result` - тег события для журнала (:func:`torrcast.ports.journal.slot.journal`),
    # а не надпись человеку: сосед по тому же вызову (``"error"``, ``"finished"``) уже
    # английский литерал, а не переключается языком показа. Запись в журнал не помнит,
    # каким языком её читали, - переключи её каталогом, и старые записи разошлись бы с
    # новыми при одной смене `cast --ru/--en`.
    result = "unhandled_failure"
    code = EXIT_INFRA
    try:
        code = run()
        result = "ok" if code == EXIT_OK else "failure"
        return code
    except CancelledError:
        # 🔴 TC-926. Человек снял свой вопрос сам: в stderr не уходит ничего и ошибкой в
        # след это не пишется - писать не о чем. Ветка стоит ПЕРЕД `TorrcastError`, иначе
        # отмена вышла бы отказом: род у неё наш, и общая ветка её проглотила бы.
        code = EXIT_CANCELLED
        result = "cancelled"
        return EXIT_CANCELLED
    except NotFoundError as exc:
        code = EXIT_NOT_FOUND
        result = "not_found"
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_NOT_FOUND
    except TorrcastError as exc:  # InfraError и всё прочее наше
        code = EXIT_INFRA
        result = "failure"
        # Слово отказа - для экрана, который ждёт этот подъём: консоль скажет свою
        # строку, а страница скажет свою по этому слову. Команда тут любая, и запись от
        # `cast status` до следующего подъёма никому не мешает: взятие поручения её
        # стирает (:meth:`hass.orders.Orders.take`).
        refusal_record().record(_refusal_of(exc))
        journal().emit("error", "error", text=str(exc)[:200])
        print(str(exc), file=sys.stderr)
        return EXIT_INFRA
    except _Stopped:  # `cast stop` - штатный конец показа, а не отказ
        code = EXIT_OK
        result = "stopped"
        return EXIT_OK
    except _Terminated:
        code = EXIT_INFRA
        result = "sigterm"
        print(phrase("cli.terminated_by_sigterm"), file=sys.stderr)
        return EXIT_INFRA
    except KeyboardInterrupt:
        code = EXIT_INFRA
        result = "keyboard_interrupt"
        print(phrase("cli.terminated_by_keyboard"), file=sys.stderr)
        return EXIT_INFRA
    except BrokenPipeError:  # `cast status | head` - не повод показывать трейсбек
        code = EXIT_OK
        result = "broken_pipe"
        with contextlib.suppress(OSError):
            sys.stdout.close()
        return EXIT_OK
    finally:
        signal.signal(signal.SIGTERM, previous)
        journal().emit("command", "finished", result=result, code=code)
        # Дожать хвост следа: фоновый писатель - демон, штатный выход обязан его дождаться.
        journal().shutdown()
