"""Одно обновление индекса серий IMDb отдельным процессом с низким приоритетом.

Сборка - полминуты чистого Python над девятью миллионами строк: в процессе службы она
держала бы GIL у ответов карточки. Отдельный процесс под ``nice`` отнимает у службы
только ядро, которое и так простаивает; выгрузка не менялась - он выходит после
заголовков ответа (:func:`.build.build`).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

#: Потолок одной сборки: выгрузка 55 МБ качается и собирается за минуту-другую.
TIMEOUT = 1800.0
Run = Callable[[Sequence[str]], int]


def refresh(url: str, target: Path, run: Run | None = None) -> bool:
    """Запустить сборку и дождаться её; ``True`` - процесс отработал без ошибки."""
    polite = [nice, "-n", "19"] if (nice := shutil.which("nice")) else []
    command = [*polite, sys.executable, "-m", f"{__package__}.build", url, str(target)]
    try:
        return (run or _run)(command) == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run(command: Sequence[str]) -> int:
    done = subprocess.run(command, check=False, timeout=TIMEOUT, capture_output=True)
    return done.returncode


__all__ = ["refresh"]
