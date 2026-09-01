"""Проверяет ответ «идёт ли показ»: живым считается ровно запущенное задание."""

from __future__ import annotations

import subprocess

import pytest

from torrcast.adapters.launchd._launchd_call import LaunchdCall
from torrcast.adapters.launchd.job_active import job_active


def _prints(answer: str, code: int = 0) -> LaunchdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], code, answer, "")

    return call


@pytest.mark.parametrize(
    ("answer", "alive"),
    [
        ("\tstate = running\n", True),
        # Первые миллисекунды после ``bootstrap`` задание - ``xpcproxy``: launchd
        # собирает процесс, журнала ещё нет. Посчитав его мёртвым, ``cast`` бросал
        # живой показ на первом опросе с «в журнале пусто» вместо настоящей причины.
        ("\tstate = xpcproxy\n", True),
        ("\tstate = not running\n", False),
        # Регистрация переживает процесс: «знает такое задание» - ещё не «показ идёт».
        ("\tstate = not running\n\tlast exit code = 0\n", False),
        # Вложенные секции ``print`` со своими ``state`` за показ не считаются.
        ("\tstate = not running\n\tsockets = {\n\t\tstate = xpcproxy\n\t}\n", False),
        ("", False),
    ],
)
def test_only_a_running_job_counts_as_a_running_show(answer: str, alive: bool) -> None:
    """``not running`` - уже не показ, хотя launchd его ещё помнит."""
    assert job_active(call=_prints(answer)) is alive


def test_a_job_launchd_does_not_know_is_not_a_show() -> None:
    """Нет такого задания - нет показа, и это не авария (код 113, а не исключение).

    Ответ об ошибке не разбирается вовсе: что бы в нём ни лежало, показом его не
    считают.
    """
    assert job_active(call=_prints("", code=113)) is False
    assert job_active(call=_prints("\tstate = running\n", code=113)) is False
