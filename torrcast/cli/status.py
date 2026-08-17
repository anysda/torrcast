"""Команда ``cast status``: что играет, где показ стоит и чем он держится.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.status_command.status_command`.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.module import module

#: Композиционный корень зовётся по имени: слой команд не вправе видеть адаптеры,
#: которыми сеанс ходит в юнит, в состояние и в TorrServer.
_SESSION: Callable[[], int] = module("torrcast.runtime.status_command").status_command


def status(command: Callable[[], int] = _SESSION) -> int:
    """``cast status`` — состояние текущего или последнего сеанса."""
    return command()
