"""Проверяет, что ключ играющего показа достаётся из окружения живого задания."""

from __future__ import annotations

import subprocess

from torrcast.adapters.launchd._launchd_call import LaunchdCall
from torrcast.adapters.launchd.job_key import job_key
from torrcast.domain.unit_naming import _JOB_KEY_ENV


def _prints(answer: str, code: int = 0) -> LaunchdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], code, answer, "")

    return call


_RUNNING = (
    f"\tstate = running\n\tenvironment = {{\n\t\t{_JOB_KEY_ENV} => movie:моана 2:2024\n\t}}\n"
)


def test_the_key_of_the_playing_show_comes_from_its_own_environment() -> None:
    """Свежайшая запись в state для этого не годится: рядом мог писать другой ход.

    Значение ключа читается до конца строки, а не «первое слово»: ключ бывает с
    дефисами, двоеточиями и пробелами внутри.
    """
    assert job_key(call=_prints(_RUNNING)) == "movie:моана 2:2024"


def test_a_dead_but_registered_job_gives_no_key() -> None:
    """Регистрация переживает процесс, и её окружение - про УЖЕ погасший показ."""
    dead = _RUNNING.replace("state = running", "state = not running")
    assert job_key(call=_prints(dead)) == ""


def test_a_job_without_our_key_gives_no_key() -> None:
    """Чужое задание, отсутствие задания и пустой ответ - не ключ."""
    stranger = "\tstate = running\n\tenvironment = {\n\t\tPATH => /usr/bin\n\t}\n"
    assert job_key(call=_prints(stranger)) == ""
    assert job_key(call=_prints("", code=113)) == ""
    assert job_key(call=_prints("")) == ""
    # Ответ об ошибке не разбирается: что бы в нём ни лежало, ключом его не считают.
    assert job_key(call=_prints(_RUNNING, code=113)) == ""
