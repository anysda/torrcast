"""Команда ``cast status``: что играет, где показ стоит и чем он держится.
Зовёт её :func:`torrcast.cli.main.main`, сценарий ей собирает
:func:`torrcast.runtime.status_command.status_command`.
"""

from __future__ import annotations

from collections.abc import Callable

#: Кем отвечает ``cast status``. Кладёт сюда композиционный корень
#: (:mod:`torrcast.runtime.wire`): слой команд не вправе видеть адаптеры, которыми сеанс
#: ходит в юнит, в состояние и в TorrServer. До слова корня имени тут нет вовсе - прежде
#: команда доставала сеанс строкой с именем модуля, тем же обходом, что и плоский фасад.
_SESSION: Callable[[], int]


def _configure_status(session: Callable[[], int]) -> None:
    """Назначить, каким сеансом отвечает ``cast status``."""
    global _SESSION
    _SESSION = session


def status(command: Callable[[], int] | None = None) -> int:
    """``cast status`` — состояние текущего или последнего сеанса."""
    return (_SESSION if command is None else command)()
