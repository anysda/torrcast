"""Команда ``cast stop``: снять каст и зафиксировать позицию.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.stop_command.stop_command`.
"""

from __future__ import annotations

from collections.abc import Callable

#: Кем отвечает ``cast stop``. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): слой команд не вправе видеть адаптеры, которыми сеанс
#: гасит юнит и убирает за собой раздачу.
_SESSION: Callable[[], int]


def _configure_stop(session: Callable[[], int]) -> None:
    """Назначить, каким сеансом отвечает ``cast stop``."""
    global _SESSION
    _SESSION = session


def stop(command: Callable[[], int] | None = None) -> int:
    """``cast stop`` — остановить показ и сказать сохранённую позицию."""
    return (_SESSION if command is None else command)()
