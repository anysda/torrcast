"""Ответ командной строки: чем бы команда ни кончилась, наружу идёт код возврата."""

from __future__ import annotations

import os
import signal
from collections.abc import Callable

import pytest

from torrcast.cli.answered import answered
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
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


@pytest.mark.parametrize(
    ("run", "result", "code"),
    [
        (lambda: int(EXIT_OK), "успех", EXIT_OK),
        (_broken, "необработанный отказ", EXIT_INFRA),
    ],
)
def test_every_exit_closes_the_trace(run: Callable[[], int], result: str, code: int) -> None:
    """Штатный конец и отказ оставляют последнюю запись до остановки писателя."""
    tape = _ClosingTape()
    install(tape)

    if result == "необработанный отказ":
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
