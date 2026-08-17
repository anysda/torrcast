"""Команда ``cast stop``: снять каст и зафиксировать позицию.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.stop_command.stop_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.module import module

#: Композиционный корень зовётся по имени: слой команд не вправе видеть адаптеры,
#: которыми сеанс гасит юнит и убирает за собой раздачу.
_SESSION: Callable[[], int] = module("torrcast.runtime.stop_command").stop_command


def stop(command: Callable[[], int] = _SESSION) -> int:
    """``cast stop`` — остановить показ и сказать сохранённую позицию."""
    return command()
