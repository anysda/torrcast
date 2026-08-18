"""Зовёт systemd в той области, где живут наши transient-юниты показа.

Общий помощник команд юнита (:func:`start_play_unit` и соседи): область у них одна,
и решается она одинаково.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from typing import TypeAlias

#: Чем команда юнита зовёт systemd. Боевое умолчание у всех команд одно и то же
#: (:func:`_systemd`), поэтому продукт про этот довод не знает вовсе; стенду он нужен,
#: чтобы не лезть в модуль соседа за именем и не заводить настоящих юнитов на машине.
SystemdCall: TypeAlias = Callable[..., subprocess.CompletedProcess[str]]


def _scope() -> list[str]:
    """Юнит системный, когда мы root (так после ``install.sh``), иначе
    пользовательский (так на dev). Постоянных юнитов у нас нет ни там, ни там — только
    transient на время показа.
    """
    return [] if os.geteuid() == 0 else ["--user"]


def _systemd(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [tool, *_scope(), *args], capture_output=True, text=True, check=False, timeout=60
    )
