"""Ответ командной строки: чем бы команда ни кончилась, наружу идёт код возврата."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Callable

import pytest

from torrcast.cli.answered import answered
from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.exit_codes import EXIT_CANCELLED, EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.stopped import _on_term


class _ClosingTape(Silent):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []
        self.closed = 0

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.events.append((phase, event, fields))

    def shutdown(self) -> None:
        self.closed += 1


def _broken() -> int:
    raise RuntimeError("сломано")


def test_a_planned_stop_of_the_show_is_a_success_not_a_failure() -> None:
    """`cast stop` обязан оставлять юнит кодом 0.

    SIGTERM от `cast stop` поднимает исключение — иначе показ не пройдёт через ``finally``
    и не запишет позицию. Но исключение это штатное, и выходить на нём кодом 2 нельзя:
    systemd помечает юнит ``failed``, и после каждой нормальной остановки пользователь видит
    красную строку в статусе. Ctrl-C на вопросе отказом при этом быть не перестаёт.

    Команда сюда приходит аргументом (:func:`torrcast.cli.answered.answered`) - тем же путём,
    каким её отдаёт разбор аргументов боевого запуска.
    """
    caught: list[BaseException] = []

    def terminated() -> int:
        try:
            _on_term(15, None)
        except BaseException as exc:  # ловим ровно затем, чтобы посмотреть на него
            caught.append(exc)
            raise
        return int(EXIT_OK)

    assert answered(terminated) == EXIT_OK, "`cast stop` - успех показа, а не отказ"
    assert isinstance(caught[0], KeyboardInterrupt), "раскрутка обязана идти как прежде"

    def interrupted() -> int:
        raise KeyboardInterrupt

    assert answered(interrupted) == EXIT_INFRA, "Ctrl-C остаётся отказом"


def test_a_cancelled_question_is_its_own_code_and_says_nothing_out_loud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-926. Человек снял вопрос сам: своё число, тишина в stderr, след без ошибки.

    Рядом стоит настоящий отказ той же породы (`NotFoundError` - тоже `TorrcastError`):
    он по-прежнему кричит в stderr и уходит кодом 1. Одно от другого разводит РОД
    исключения, а не молчание на всё подряд.
    """
    tape = _ClosingTape()
    install(tape)

    def cancelled() -> int:
        raise CancelledError("человек передумал")

    assert answered(cancelled) == EXIT_CANCELLED
    assert capsys.readouterr().err == "", "отмена ничего не ломала - и кричать ей не о чем"
    assert tape.events == [("command", "finished", {"result": "cancelled", "code": EXIT_CANCELLED})]

    def missing() -> int:
        raise NotFoundError("ничего не нашёл")

    assert answered(missing) == EXIT_NOT_FOUND
    assert capsys.readouterr().err == "ничего не нашёл\n"


@pytest.mark.parametrize(
    ("run", "result", "code"),
    [
        (lambda: int(EXIT_OK), "ok", EXIT_OK),
        (_broken, "unhandled_failure", EXIT_INFRA),
    ],
)
def test_every_exit_closes_the_trace(run: Callable[[], int], result: str, code: int) -> None:
    """Штатный конец и отказ оставляют последнюю запись до остановки писателя."""
    tape = _ClosingTape()
    install(tape)

    if result == "unhandled_failure":
        with pytest.raises(RuntimeError, match="сломано"):
            answered(run)
    else:
        assert answered(run) == code

    assert tape.events == [("command", "finished", {"result": result, "code": code})]
    assert tape.closed == 1


def test_sigterm_is_named_on_the_screen_and_in_the_trace(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SIGTERM раскручивает общий выход, сообщает причину и дожимает ленту."""
    tape = _ClosingTape()
    install(tape)

    def terminated() -> int:
        os.kill(os.getpid(), signal.SIGTERM)
        return int(EXIT_OK)

    assert answered(terminated) == EXIT_INFRA
    assert capsys.readouterr().err == "команда прервана сигналом SIGTERM\n"
    assert tape.events == [("command", "finished", {"result": "SIGTERM", "code": EXIT_INFRA})]
    assert tape.closed == 1


@pytest.mark.machine
def test_cast_process_still_catches_sigterm() -> None:
    """Обычный процесс CLI ловит SIGTERM; бот не покупается ослаблением сторожа."""
    script = """
import os
import signal
from torrcast.cli.main import main
from torrcast.runtime.wire import wire

wire()
commands = {"play": lambda _args: os.kill(os.getpid(), signal.SIGTERM)}
raise SystemExit(main(["мумия"], commands=commands))
"""
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False, timeout=10
    )

    assert done.returncode == EXIT_INFRA
    assert "команда прервана сигналом SIGTERM" in done.stderr
