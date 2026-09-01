"""Зовёт launchd в той области, где живут наши задания показа.

Общий помощник команд задания (:func:`start_play_job` и соседи): область у них одна,
и решается она одинаково.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import TypeAlias

#: Чем команда задания зовёт launchd. Боевое умолчание у всех команд одно и то же
#: (:func:`_launchd`), поэтому продукт про этот довод не знает вовсе; стенду он нужен,
#: чтобы не лезть в модуль соседа за именем и не заводить настоящих заданий на машине.
LaunchdCall: TypeAlias = Callable[..., subprocess.CompletedProcess[str]]


def _domain() -> str:
    """Задание системное, когда мы root (так после ``install.sh``), иначе
    пользовательское - ``gui/$UID``. Выбран ``gui``, а не ``user``: это область
    LaunchAgent'ов, и процессы в ней не умирают с закрытием терминала или обрывом
    ssh - ради чего вся затея. Постоянных заданий у нас нет ни там, ни там - только
    на время показа.
    """
    uid = os.geteuid()
    return "system" if uid == 0 else f"gui/{uid}"


def _running(answer: str) -> bool:
    """Жив ли процесс задания по ответу ``launchctl print``.

    Регистрация задания переживает его процесс (аналога ``--collect`` у launchd нет),
    поэтому меряется не «знает ли launchd такое задание», а его состояние: у мёртвого
    оно ``not running``. Строка состояния читается только на верхнем уровне ответа -
    вглубь (по сокетам и конечным точкам) у задания свои ``state``, и чужая ``active``
    объявила бы живым погасший показ.
    """
    return "\tstate = running" in answer.splitlines()


def _launchd(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([tool, *args], capture_output=True, text=True, check=False, timeout=60)
